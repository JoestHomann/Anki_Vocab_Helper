import base64
from contextlib import nullcontext
import importlib
import io
import json
from pathlib import Path
import sys
import types
import threading
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen
from urllib.error import HTTPError
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if 'spanish_helper' not in sys.modules:
    package = types.ModuleType('spanish_helper'); package.__path__ = [str(ROOT / 'spanish_helper')]
    sys.modules['spanish_helper'] = package
plan = importlib.import_module('spanish_helper.chatgpt')
windows = importlib.import_module('spanish_helper.windows_auth')
FIXTURE = json.loads((ROOT / 'tests/fixtures/oidc_rs256.json').read_text())


class ChatGPTTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Native Windows cryptography')
    def test_native_signature_validation_and_tamper_rejection(self):
        claims = plan.validate_identity(FIXTURE['token'], 'test-client', 'test-nonce', FIXTURE['jwks'], now=1000000)
        self.assertEqual(claims['sub'], 'synthetic-test-account')
        header, body, signature = FIXTURE['token'].split('.')
        changed = json.loads(plan._decode(body)); changed['sub'] = 'forged-account'
        body = base64.urlsafe_b64encode(json.dumps(changed).encode()).decode().rstrip('=')
        with self.assertRaises(plan.AuthError):
            plan.validate_identity('.'.join([header, body, signature]), 'test-client', 'test-nonce', FIXTURE['jwks'], now=1000000)

    def test_nonce_audience_expiry_and_algorithm_are_required(self):
        with patch.object(plan, 'verify_rs256'):
            for client, nonce, now in [('wrong-client','test-nonce',1000000),('test-client','wrong-nonce',1000000),('test-client','test-nonce',4102444801)]:
                with self.assertRaises(plan.AuthError):
                    plan.validate_identity(FIXTURE['token'], client, nonce, FIXTURE['jwks'], now=now)
            parts = FIXTURE['token'].split('.')
            parts[0] = base64.urlsafe_b64encode(b'{"alg":"none","kid":"synthetic-test-key"}').decode().rstrip('=')
            with self.assertRaises(plan.AuthError):
                plan.validate_identity('.'.join(parts), 'test-client', 'test-nonce', FIXTURE['jwks'])

    @unittest.skipUnless(sys.platform == 'win32', 'Native Windows encryption')
    def test_native_protection_round_trip(self):
        raw = b'synthetic-session-storage-test'
        protected = windows.protect(raw)
        self.assertNotIn(raw, protected)
        self.assertEqual(windows.protect(protected, decrypt=True), raw)

    def test_stream_requires_completion_and_uses_subscription_parameters(self):
        payload = {'model':'test-plan-model','input':'word data','max_output_tokens':600,'instructions':'review','store':True}
        complete = {'type':'response.completed','response':{'status':'completed','output':[]}}
        stream = io.BytesIO(b'data: ' + json.dumps(complete).encode() + b'\n\n')
        with patch.object(plan, '_access', return_value='synthetic-access'), patch.object(plan, 'urlopen', return_value=stream) as open_url:
            raw, _ = plan.response('test-profile', payload)
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertNotIn('max_output_tokens', sent)
        self.assertTrue(sent['stream']); self.assertFalse(sent['store'])
        self.assertEqual(sent['input'], [{'role':'user','content':'word data'}])
        self.assertEqual(json.loads(raw)['status'], 'completed')
        self.assertEqual(open_url.call_args.args[0].full_url, 'https://api.openai.com/v1/responses')

    def test_failed_interrupted_and_incomplete_streams_are_errors(self):
        for content in [b'', b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n',
                        b'data: {"type":"response.failed","response":{"error":{"code":"subscription_sharing_usage_limit_exceeded"}}}\n\n',
                        b'data: {"type":"response.incomplete"}\n\n']:
            with patch.object(plan, '_access', return_value='synthetic'), patch.object(plan, 'urlopen', return_value=io.BytesIO(content)):
                with self.assertRaises(plan.AuthError):
                    plan.response('test-profile', {'model':'test','input':'word'})

    def test_refresh_rotates_tokens_and_never_uses_dynamic_client(self):
        account = dict(client_id='issued-client',access_token='old-access',refresh_token='old-refresh',expires_at=0,scopes=['chatgpt.tokens.use.direct'])
        data = {'active':'issued-client','accounts':[account]}
        with patch.object(plan, '_locked', return_value=nullcontext()), patch.object(plan, '_load', return_value=data), patch.object(plan, '_save') as save, patch.object(plan, '_request', return_value={'access_token':'new-access','refresh_token':'new-refresh','expires_in':3600}) as request:
            self.assertEqual(plan._access('profile'), 'new-access')
        self.assertEqual(request.call_args.args[1]['client_id'], 'issued-client')
        self.assertNotIn('scope', request.call_args.args[1])
        self.assertEqual(save.call_args.args[1]['accounts'][0]['refresh_token'], 'new-refresh')

    def test_disconnected_or_declined_plan_is_not_used(self):
        for data in [{'active':'','accounts':[]}, {'active':'issued','accounts':[{'client_id':'issued'}]}]:
            with patch.object(plan, '_locked', return_value=nullcontext()), patch.object(plan, '_load', return_value=data), patch.object(plan, '_request') as request:
                with self.assertRaises(plan.AuthError):
                    plan._access('profile')
                request.assert_not_called()

    def test_sign_out_preserves_registration_but_removes_tokens(self):
        data = {'active':'issued', 'accounts':[{'client_id':'issued','subject':'sub','refresh_token':'refresh','access_token':'access','id_token':'identity'}]}
        with patch.object(plan, '_locked', return_value=nullcontext()), patch.object(plan, '_load', return_value=data), patch.object(plan, '_save'), patch.object(plan, '_discovery', return_value={'revocation_endpoint':plan.AUTH+'/revoke'}), patch.object(plan, '_request'):
            self.assertTrue(plan.sign_out('profile'))
        self.assertEqual(data['active'], '')
        self.assertNotIn('refresh_token',data['accounts'][0])
        self.assertNotIn('access_token',data['accounts'][0])
        self.assertNotIn('id_token',data['accounts'][0])
        self.assertEqual(data['accounts'][0]['client_id'],'issued')

    def test_loopback_sign_in_binds_state_pkce_callback_and_issued_client(self):
        data = {'host_id':'urn:uuid:synthetic-host','accounts':[],'active':''}
        captured = {}
        workers = []
        def browser(url):
            query = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
            captured.update(query)
            def callback():
                try:
                    urlopen(query['redirect_uri'] + '?' + urlencode({'state':'wrong-state','code':'bad'}), timeout=5)
                except HTTPError as error:
                    self.assertEqual(error.code,400)
                urlopen(query['redirect_uri'] + '?' + urlencode({'state':query['state'],'code':'synthetic-code','client_id':'issued-client'}), timeout=5).close()
            worker = threading.Thread(target=callback); worker.start(); workers.append(worker)
            return True
        def request(url, data=None, **kwargs):
            if url.endswith('/oauth/token'):
                self.assertTrue(any(a['client_id'] == 'issued-client' for a in save.call_args.args[1]['accounts']))
                self.assertEqual(data['client_id'],'issued-client')
                self.assertEqual(data['redirect_uri'],captured['redirect_uri'])
                challenge=base64.urlsafe_b64encode(__import__('hashlib').sha256(data['code_verifier'].encode()).digest()).decode().rstrip('=')
                self.assertEqual(challenge,captured['code_challenge'])
                return {'id_token':'synthetic-id','access_token':'synthetic-access','refresh_token':'synthetic-refresh', 'scope':plan.SCOPE,'expires_in':3600}
            return {'keys':[]}
        with patch.object(plan,'_locked',return_value=nullcontext()), patch.object(plan,'_load',return_value=data), patch.object(plan,'_save') as save, patch.object(plan.webbrowser,'open',side_effect=browser), patch.object(plan,'_request',side_effect=request), patch.object(plan,'_discovery',return_value={'jwks_uri':plan.AUTH+'/jwks'}), patch.object(plan,'validate_identity',return_value={'sub':'synthetic-account','email':'test@example.invalid'}) as validate:
            result=plan.sign_in('synthetic-profile', timeout=10)
        for worker in workers:
            worker.join(timeout=5)
        self.assertEqual(result['label'],'test@example.invalid')
        self.assertEqual(captured['client_id'],'dynamic_agent_client')
        self.assertEqual(captured['resource'],plan.RESOURCE)
        self.assertEqual(captured['ext_agent_host_id'],'urn:uuid:synthetic-host')
        self.assertEqual(validate.call_args.args[2],captured['nonce'])
        self.assertEqual(save.call_args.args[1]['active'],'issued-client')


if __name__ == '__main__':
    unittest.main()
