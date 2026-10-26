import importlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock

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
        request = Mock(return_value=response(result))
        checked = services.check_translation(context, 'gpt-6-luna', requester=request)
        self.assertEqual(checked['saved'], 'verlegen')
        self.assertEqual(checked['suggestion'], 'schwanger')
        self.assertEqual(checked['verdict'], 'incorrect')
        payload = request.call_args.args[0]
        self.assertFalse(payload['store'])
        self.assertEqual(payload['reasoning'], {'effort': 'none'})
        self.assertNotIn('max_output_tokens', payload)
        self.assertTrue(payload['text']['format']['strict'])
        sent = json.loads(payload['input'])
        self.assertEqual(sent['espanol'], 'embarazada')
        self.assertEqual(sent['traduccion_guardada'], 'verlegen')
        self.assertNotIn('Untrusted saved hint', json.dumps(payload))

    def test_valid_synonym_and_uncertainty_do_not_require_correction(self):
        for verdict in ('correct', 'uncertain'):
            with self.subTest(verdict=verdict):
                request = Mock(return_value=response(
                    {'verdict': verdict, 'explanation': 'Hay varias acepciones posibles.', 'suggestion': ''}))
                self.assertEqual(services.check_translation(core.CardContext('piso', meaning='Stockwerk'),
                    'test-plan-model', requester=request)['verdict'], verdict)

    def test_missing_fields_and_oversized_inputs_make_no_request(self):
        for context in (core.CardContext('hola'), core.CardContext('', meaning='Hallo'),
                        core.CardContext('x' * 181, meaning='Hallo'),
                        core.CardContext('hola', meaning='x' * 501)):
            with self.subTest(context=context):
                request = Mock()
                with self.assertRaises(services.HelperError):
                    services.check_translation(context, 'test-plan-model', requester=request)
                request.assert_not_called()

    def test_incomplete_refused_and_invalid_verdicts_never_look_successful(self):
        valid = {'verdict': 'correct', 'explanation': 'Es una traducción válida.', 'suggestion': ''}
        invalid = [response(valid, 'incomplete'), response({**valid, 'verdict': 'maybe'}),
                   response({**valid, 'explanation': ' '}), response({**valid, 'suggestion': None}),
                   response({**valid, 'verdict': 'incorrect'}),
                   (b'{"status":"completed","output":[{"content":[{"type":"refusal"}]}]}', 'application/json'),
                   (b'not-json', 'application/json'), (b'[]', 'application/json')]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(services.HelperError):
                    services.check_translation(core.CardContext('hola', meaning='Hallo'), 'test-plan-model', requester=Mock(return_value=value))

    def test_custom_translation_field_overrides_detected_back(self):
        fields = {'Spanish': 'ahorrar', 'Back': 'wrong old field', 'Deutsch': '<b>sparen</b>'}
        context = core.extract_context(fields, 'ahorrar sparen', {'translation_field': 'Deutsch'})
        self.assertEqual(context.meaning, 'sparen')
        self.assertEqual(core.extract_context(fields, 'ahorrar', {'translation_field': 'Missing'}).meaning, '')

    def test_custom_model_does_not_receive_unsupported_reasoning_parameter(self):
        request = Mock(return_value=response(
            {'verdict': 'correct', 'explanation': 'Es válida.', 'suggestion': ''}))
        services.check_translation(core.CardContext('hola', meaning='Hallo'), 'custom-model', requester=request)
        self.assertNotIn('reasoning', request.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
