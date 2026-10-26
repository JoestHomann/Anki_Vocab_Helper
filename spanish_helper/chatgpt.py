"""Official ChatGPT plan OAuth and Responses streaming; never falls back to paid API keys."""
import base64
from contextlib import contextmanager
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4
import webbrowser

from .windows_auth import AuthError, protect, verify_rs256

AUTH = 'https://auth.openai.com'
RESOURCE = 'https://api.openai.com/v1'
SCOPE = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
USAGE_URL = 'https://chatgpt.com/settings/usage'
ROOT = Path(__file__).parent / 'user_files' / 'chatgpt'
LOCK = threading.RLock()


def _path(profile):
    digest = hashlib.sha256(os.path.normcase(os.path.abspath(profile)).encode()).hexdigest()
    return ROOT / (digest + '.enc')


@contextmanager
def _locked(profile):
    import msvcrt
    with LOCK:
        ROOT.mkdir(parents=True, exist_ok=True)
        with open(str(_path(profile)) + '.lock', 'a+b') as lock:
            lock.seek(0)
            if not lock.read(1):
                lock.write(b'0'); lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def _load(profile):
    path = _path(profile)
    if not path.exists():
        return {'host_id': 'urn:uuid:' + str(uuid4()), 'accounts': [], 'active': ''}
    try:
        return json.loads(protect(path.read_bytes(), decrypt=True))
    except (ValueError, OSError):
        raise AuthError('Cannot read your ChatGPT session. Open settings to reconnect.') from None


def _save(profile, data):
    ROOT.mkdir(parents=True, exist_ok=True)
    path = _path(profile)
    encoded = protect(json.dumps(data).encode())
    temporary = path.with_suffix('.' + secrets.token_hex(8) + '.tmp')
    try:
        with open(temporary, 'xb') as file:
            file.write(encoded); file.flush(); os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _request(url, data=None, token='', form=False):
    headers = {'User-Agent': 'AnkiSpanishHelper/1.3', 'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    body = None
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        body = (urlencode(data) if form else json.dumps(data)).encode()
    try:
        with urlopen(Request(url, data=body, headers=headers), timeout=35) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise AuthError('The ChatGPT response is too large.')
            return json.loads(raw) if raw else {}
    except HTTPError as error:
        if error.code == 429:
            raise AuthError('A ChatGPT plan or app limit has been reached. Check ChatGPT → Settings → Usage.') from None
        raise AuthError('ChatGPT could not complete the request. Check your connection and sign in again if needed.') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise AuthError('Cannot connect to ChatGPT. Check your internet connection and try again.') from None


def _decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def validate_identity(token, client_id, nonce, jwks, now=None):
    try:
        header64, claims64, signature64 = token.split('.')
        header, claims = json.loads(_decode(header64)), json.loads(_decode(claims64))
        if header.get('alg') != 'RS256' or not header.get('kid') or header.get('crit'):
            raise ValueError()
        keys = [key for key in jwks['keys'] if key.get('kid') == header['kid'] and key.get('kty') == 'RSA']
        if len(keys) != 1:
            raise ValueError()
        key = keys[0]
        if key.get('alg', 'RS256') != 'RS256' or key.get('use', 'sig') != 'sig':
            raise ValueError()
        verify_rs256((header64 + '.' + claims64).encode('ascii'), _decode(signature64), _decode(key['n']), _decode(key['e']))
        audience = claims['aud'] if isinstance(claims['aud'], list) else [claims['aud']]
        current = time.time() if now is None else now
        if (claims['iss'] != AUTH or client_id not in audience or not claims.get('sub') or
                not isinstance(claims['exp'], (int, float)) or not math.isfinite(claims['exp']) or claims['exp'] <= current or
                (len(audience) > 1 and claims.get('azp') != client_id) or claims.get('azp', client_id) != client_id or
                claims.get('nbf', 0) > current + 30 or not hmac.compare_digest(str(claims.get('nonce', '')), nonce)):
            raise ValueError()
        return claims
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise AuthError('Could not verify your ChatGPT identity. This connection has not been authorized.') from None


def _discovery():
    data = _request(AUTH + '/.well-known/openid-configuration')
    if data.get('issuer') != AUTH or not str(data.get('jwks_uri', '')).startswith(AUTH + '/'):
        raise AuthError('The ChatGPT identity configuration is invalid.')
    return data


def accounts(profile):
    with _locked(profile):
        data = _load(profile)
    return {'active': data['active'], 'accounts': [
        {'client_id': a['client_id'], 'label': a.get('email') or a.get('subject') or 'Connection pending', 'connected': bool(a.get('refresh_token'))}
        for a in data['accounts']]}


def select_account(profile, client_id):
    with _locked(profile):
        data = _load(profile)
        if not any(a['client_id'] == client_id for a in data['accounts']):
            raise AuthError('Select a connected ChatGPT account.')
        data['active'] = client_id; _save(profile, data)


def sign_in(profile, client_id='', timeout=240):
    with _locked(profile):
        data = _load(profile)
        _save(profile, data)  # Persist the host before opening the browser.
        existing = next((a.copy() for a in data['accounts'] if a['client_id'] == client_id), None)
    verifier, state, nonce = secrets.token_urlsafe(48), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    result = {}
    class Callback(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(5)
            super().setup()
        def log_message(self, *args):
            pass  # Callback codes and tokens must never enter logs.
        def do_GET(self):
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            if parts.path != '/auth/callback' or not hmac.compare_digest(query.get('state', [''])[0], state):
                self.send_error(400); return
            if any(len(values) != 1 for values in query.values()):
                self.send_error(400); return
            result.update({key: values[0] for key, values in query.items()})
            body = b'Continue in Anki. You may close this browser tab.'
            self.send_response(200); self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(body)
    with HTTPServer(('127.0.0.1', 0), Callback) as server:
        server.timeout = 1
        redirect = 'http://127.0.0.1:' + str(server.server_port) + '/auth/callback'
        params = dict(client_id=existing['client_id'] if existing else 'dynamic_agent_client',
                      ext_agent_host_id=data['host_id'], response_type='code', redirect_uri=redirect,
                      scope=SCOPE, resource=RESOURCE, state=state, nonce=nonce, code_challenge_method='S256',
                      code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='))
        if not existing:
            params['agent_name_hint'] = 'Anki Spanish Helper'
        if not webbrowser.open(AUTH + '/api/accounts/authorize?' + urlencode(params)):
            raise AuthError('Could not open your browser to sign in with ChatGPT.')
        deadline = time.monotonic() + timeout
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if not result or result.get('error') or not result.get('code'):
        raise AuthError('Sign-in was cancelled or timed out. You can try again.')
    issued = result.get('client_id', client_id)
    if not issued or issued == 'dynamic_agent_client' or (existing and issued != existing['client_id']):
        raise AuthError('ChatGPT did not return a valid registration for this account.')
    # Keep the issued registration even if code exchange or validation fails.
    # It is not an authorized account until identity and granted scopes validate.
    with _locked(profile):
        registration = _load(profile)
        if not any(a['client_id'] == issued for a in registration['accounts']):
            registration['accounts'].append(dict(client_id=issued, subject='', email='', welcome_shown=False))
            _save(profile, registration)
    tokens = _request(AUTH + '/api/accounts/oauth/token', dict(grant_type='authorization_code', client_id=issued,
                      code=result['code'], code_verifier=verifier, redirect_uri=redirect, resource=RESOURCE), form=True)
    discovery = _discovery()
    identity = validate_identity(tokens.get('id_token', ''), issued, nonce, _request(discovery['jwks_uri']))
    if existing and existing.get('subject') and identity['sub'] != existing['subject']:
        raise AuthError('The authorized account does not match the selected account. Use Add an account to connect it.')
    if 'chatgpt.tokens.use.direct' not in str(tokens.get('scope', '')).split() or not tokens.get('refresh_token') or not tokens.get('access_token'):
        raise AuthError('ChatGPT plan usage was not authorized. Reconnect and allow access to your plan.')
    first = not existing or not existing.get('welcome_shown')
    account = dict(client_id=issued, subject=identity['sub'], email=identity.get('email', ''), id_token=tokens['id_token'], welcome_shown=True,
                   access_token=tokens['access_token'], refresh_token=tokens['refresh_token'],
                   scopes=tokens['scope'].split(), expires_at=time.time() + float(tokens['expires_in']))
    account['earliest_refresh_at'] = float(tokens.get('earliest_refresh_at', 0))
    with _locked(profile):
        data = _load(profile)
        data['accounts'] = [a for a in data['accounts'] if a['client_id'] != issued] + [account]
        data['active'] = issued; _save(profile, data)
    return {'label': account['email'] or account['subject'], 'first': first}


def _access(profile):
    with _locked(profile):
        data = _load(profile)
        account = next((a for a in data['accounts'] if a['client_id'] == data['active']), None)
        if not account or not account.get('refresh_token'):
            raise AuthError('Open Tools → Spanish Helper and click Continue with ChatGPT to use your subscription.')
        if account['expires_at'] < time.time() + 90 and time.time() >= account.get('earliest_refresh_at', 0):
            tokens = _request(AUTH + '/api/accounts/oauth/token', dict(grant_type='refresh_token',
                              client_id=account['client_id'], refresh_token=account['refresh_token'], resource=RESOURCE), form=True)
            if not tokens.get('access_token') or not tokens.get('refresh_token'):
                raise AuthError('Reconnect your ChatGPT account to renew the session.')
            scopes = str(tokens.get('scope', ' '.join(account['scopes']))).split()
            if 'chatgpt.tokens.use.direct' not in scopes:
                raise AuthError('ChatGPT plan usage is not authorized. Reconnect in settings.')
            account.update(access_token=tokens['access_token'], refresh_token=tokens['refresh_token'], scopes=scopes,
                           expires_at=time.time() + float(tokens['expires_in']), earliest_refresh_at=float(tokens.get('earliest_refresh_at', 0)))
            _save(profile, data)
        return account['access_token']


def models(profile):
    catalog = _request(RESOURCE + '/models', token=_access(profile))
    choices = [dict(slug=item['slug'], display_name=item.get('display_name', item['slug']))
               for item in catalog.get('models', []) if item.get('visibility') == 'list' and item.get('slug')]
    if not choices:
        raise AuthError('This account has no models available for the add-on. Check your plan eligibility.')
    return choices


def sign_out(profile):
    with _locked(profile):
        data = _load(profile)
        account = next((a for a in data['accounts'] if a['client_id'] == data['active']), None)
        confirmed = True
        if account and account.get('refresh_token'):
            try:
                endpoint = _discovery()['revocation_endpoint']
                if not endpoint.startswith(AUTH + '/'):
                    raise AuthError('Cannot revoke this session automatically.')
                _request(endpoint, dict(token=account['refresh_token'], token_type_hint='refresh_token', client_id=account['client_id']), form=True)
            except (AuthError, KeyError):
                confirmed = False
            for name in ('access_token', 'refresh_token', 'id_token'):
                account.pop(name, None)
        data['active'] = ''; _save(profile, data)
    return confirmed


def response(profile, payload):
    token = _access(profile)
    payload = {key: value for key, value in payload.items() if key not in ('max_output_tokens', 'temperature', 'top_p')}
    conversation = payload['input']
    if isinstance(conversation, str):
        conversation = [{'role': 'user', 'content': conversation}]
    payload.update(store=False, stream=True, input=conversation)
    request = Request(RESOURCE + '/responses', data=json.dumps(payload).encode(),
                      headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', 'Accept': 'text/event-stream'})
    try:
        with urlopen(request, timeout=60) as stream:
            size, event_lines = 0, []
            output_items, output_parts = {}, {}
            for line in stream:
                size += len(line)
                if size > 2_000_000:
                    raise AuthError('The ChatGPT response is too large.')
                if line.strip():
                    if line.startswith(b'data:'):
                        event_lines.append(line[5:].strip())
                    continue
                if not event_lines:
                    continue
                event = json.loads(b'\n'.join(event_lines)); event_lines = []
                kind = event.get('type')
                # Subscription streams may leave the terminal output array empty.
                # Retain finalized items/parts, but expose them only after completion.
                if kind == 'response.output_item.done':
                    output_items[event['output_index']] = event['item']
                elif kind in ('response.output_text.done', 'response.content_part.done'):
                    part = event['part'] if kind == 'response.content_part.done' else {'type': 'output_text', 'text': event['text']}
                    output_parts.setdefault(event['output_index'], {})[event['content_index']] = part
                elif kind == 'response.completed':
                    completed = event['response']
                    if not completed.get('output'):
                        for index, parts in output_parts.items():
                            item = output_items.setdefault(index, {'type': 'message', 'role': 'assistant'})
                            if not item.get('content'):
                                item['content'] = [parts[key] for key in sorted(parts)]
                        completed['output'] = [output_items[index] for index in sorted(output_items)]
                    return json.dumps(completed).encode(), 'application/json'
                if kind in ('response.failed', 'response.incomplete', 'error'):
                    raise AuthError('ChatGPT did not complete the check. Check ChatGPT → Settings → Usage; a plan or app limit may have been reached.')
    except HTTPError as error:
        if error.code in (403, 429):
            raise AuthError('Your ChatGPT plan is unavailable or has reached a limit. Check ChatGPT → Settings → Usage.') from None
        raise AuthError('Could not complete the check using your ChatGPT plan. Reconnect in settings.') from None
    except (URLError, OSError, ValueError):
        raise AuthError('The ChatGPT connection was interrupted. Please try again.') from None
    raise AuthError('ChatGPT did not confirm that the check completed. Please try again.')
