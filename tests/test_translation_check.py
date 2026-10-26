import importlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if 'spanish_helper' not in sys.modules:
    package = types.ModuleType('spanish_helper')
    package.__path__ = [str(ROOT / 'spanish_helper')]
    sys.modules['spanish_helper'] = package
core = importlib.import_module('spanish_helper.core')
services = importlib.import_module('spanish_helper.services')


def response(result, status='completed'):
    return json.dumps({'status': status, 'output': [{'content': [
        {'type': 'output_text', 'text': json.dumps(result)}]}]}).encode(), 'application/json'


class TranslationCheckTests(unittest.TestCase):
    def test_checks_saved_pair_with_bounded_structured_request(self):
        result = {'verdict': 'incorrect', 'explanation': '«Embarazada» no significa avergonzada.', 'suggestion': 'schwanger'}
        context = core.CardContext('embarazada', example='Ana está embarazada.', explanation='Untrusted saved hint', meaning='verlegen')
        with patch.object(services, 'request_bytes', return_value=response(result)) as request:
            checked = services.check_translation(context, 'sk-test-secret', 'gpt-6-luna')
        self.assertEqual(checked['saved'], 'verlegen')
        self.assertEqual(checked['suggestion'], 'schwanger')
        self.assertEqual(checked['verdict'], 'incorrect')
        url, payload, key = request.call_args.args
        self.assertEqual(url, 'https://api.openai.com/v1/responses')
        self.assertEqual(key, 'sk-test-secret')
        self.assertFalse(payload['store'])
        self.assertEqual(payload['reasoning'], {'effort': 'none'})
        self.assertLessEqual(payload['max_output_tokens'], 600)
        self.assertTrue(payload['text']['format']['strict'])
        sent = json.loads(payload['input'])
        self.assertEqual(sent['espanol'], 'embarazada')
        self.assertEqual(sent['traduccion_guardada'], 'verlegen')
        self.assertNotIn('Untrusted saved hint', json.dumps(payload))
        self.assertNotIn('sk-test-secret', json.dumps(payload))

    def test_valid_synonym_and_uncertainty_do_not_require_correction(self):
        for verdict in ('correct', 'uncertain'):
            with self.subTest(verdict=verdict), patch.object(services, 'request_bytes', return_value=response(
                    {'verdict': verdict, 'explanation': 'Hay varias acepciones posibles.', 'suggestion': ''})):
                self.assertEqual(services.check_translation(core.CardContext('piso', meaning='Stockwerk'), 'key', 'gpt-6-luna')['verdict'], verdict)

    def test_missing_fields_key_and_oversized_inputs_make_no_request(self):
        for context, key in ((core.CardContext('hola'), 'key'), (core.CardContext('', meaning='Hallo'), 'key'),
                             (core.CardContext('hola', meaning='Hallo'), ''),
                             (core.CardContext('x' * 181, meaning='Hallo'), 'key'),
                             (core.CardContext('hola', meaning='x' * 501), 'key')):
            with self.subTest(context=context, key=bool(key)), patch.object(services, 'request_bytes') as request:
                with self.assertRaises(services.HelperError):
                    services.check_translation(context, key, 'gpt-6-luna')
                request.assert_not_called()

    def test_incomplete_refused_and_invalid_verdicts_never_look_successful(self):
        valid = {'verdict': 'correct', 'explanation': 'Es una traducción válida.', 'suggestion': ''}
        invalid = [response(valid, 'incomplete'), response({**valid, 'verdict': 'maybe'}),
                   response({**valid, 'explanation': ' '}), response({**valid, 'suggestion': None}),
                   response({**valid, 'verdict': 'incorrect'}),
                   (b'{"status":"completed","output":[{"content":[{"type":"refusal"}]}]}', 'application/json'),
                   (b'not-json', 'application/json'), (b'[]', 'application/json')]
        for value in invalid:
            with self.subTest(value=value), patch.object(services, 'request_bytes', return_value=value):
                with self.assertRaises(services.HelperError):
                    services.check_translation(core.CardContext('hola', meaning='Hallo'), 'key', 'gpt-6-luna')

    def test_custom_translation_field_overrides_detected_back(self):
        fields = {'Spanish': 'ahorrar', 'Back': 'wrong old field', 'Deutsch': '<b>sparen</b>'}
        context = core.extract_context(fields, 'ahorrar sparen', {'translation_field': 'Deutsch'})
        self.assertEqual(context.meaning, 'sparen')
        self.assertEqual(core.extract_context(fields, 'ahorrar', {'translation_field': 'Missing'}).meaning, '')

    def test_custom_model_does_not_receive_unsupported_reasoning_parameter(self):
        with patch.object(services, 'request_bytes', return_value=response(
                {'verdict': 'correct', 'explanation': 'Es válida.', 'suggestion': ''})) as request:
            services.check_translation(core.CardContext('hola', meaning='Hallo'), 'key', 'custom-model')
        self.assertNotIn('reasoning', request.call_args.args[1])


if __name__ == '__main__':
    unittest.main()
