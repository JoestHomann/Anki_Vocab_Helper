import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType('spanish_helper')
package.__path__ = [str(ROOT / 'spanish_helper')]
sys.modules['spanish_helper'] = package
core = importlib.import_module('spanish_helper.core')
services = importlib.import_module('spanish_helper.services')
VOCAB = json.loads((ROOT / 'spanish_helper/vocabulary.json').read_text(encoding='utf-8'))


class ContextTests(unittest.TestCase):
    def test_rich_text_does_not_become_spoken_markup(self):
        self.assertEqual(core.plain_text('<b>¡Qué</b><br>bonito! [sound:test.mp3]<script>bad()</script>'), '¡Qué bonito!')

    def test_html_entities_and_accents_are_preserved(self):
        self.assertEqual(core.plain_text('ni&ntilde;o &amp; café'), 'niño & café')
        self.assertNotEqual(core.normalize('año'), core.normalize('ano'))

    def test_detects_spanish_visible_on_card(self):
        value = core.extract_context({'Spanish': 'ahorrar', 'Back': 'sparen'}, 'ahorrar', {})
        self.assertEqual(value.word, 'ahorrar')
        self.assertEqual(value.meaning, 'sparen')

    def test_does_not_read_hidden_spanish_field_on_reverse_card(self):
        value = core.extract_context({'Spanish': 'ahorrar', 'Translation': 'sparen'}, 'sparen', {})
        self.assertNotEqual(value.word, 'ahorrar')

    def test_explicit_mapping_supports_reverse_cards(self):
        value = core.extract_context({'Vocab ES': '<b>ahorrar</b>'}, 'sparen', {'word_field': 'Vocab ES'})
        self.assertEqual(value.word, 'ahorrar')

    def test_missing_explicit_field_does_not_speak_whole_prompt(self):
        value = core.extract_context({'Front': 'sparen'}, 'sparen', {'word_field': 'Spanish'})
        self.assertEqual(value.word, '')

    def test_long_prompt_needs_mapping_or_selection(self):
        value = core.extract_context({}, 'An instruction about which Spanish word you should write down in the following exercise today', {})
        self.assertEqual(value.word, '')

    def test_card_hints_take_priority_over_general_word_meaning(self):
        value = core.CardContext('contar', 'Cuenta hasta diez.', 'Decir los números en orden.')
        hint = core.local_hint(value, VOCAB)
        self.assertEqual(hint['example'], 'Cuenta hasta diez.')
        self.assertEqual(hint['source'], 'Tu tarjeta')

    def test_articles_and_case_do_not_block_local_hint(self):
        self.assertIn('fruta', core.local_hint(core.CardContext('La Manzana'), VOCAB)['explanation'])

    def test_unsupported_word_never_gets_a_made_up_local_hint(self):
        self.assertIsNone(core.local_hint(core.CardContext('not-a-real-word-123'), VOCAB))

    def test_stale_results_and_leaving_reviewer_are_rejected(self):
        self.assertTrue(core.is_current('new', 'new', True))
        self.assertFalse(core.is_current('old', 'new', True))
        self.assertFalse(core.is_current('new', 'new', False))


class ServicesTests(unittest.TestCase):
    def test_example_audio_keeps_entire_long_sentence_and_slow_setting(self):
        sentence = ' '.join(['Para aprender español, escuchamos el ejemplo y repetimos la frase.'] * 6)
        with patch.object(services, 'get_audio', side_effect=lambda text, cache, slow: Path(str(len(text)) + '.mp3')) as audio:
            paths = services.get_example_audio(sentence, Path('audio-cache'), slow=True)
        chunks = [call.args[0] for call in audio.call_args_list]
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(chunk) <= 180 for chunk in chunks))
        self.assertEqual(' '.join(chunks), sentence)
        self.assertEqual(len(paths), len(chunks))
        self.assertTrue(all(call.args[2] is True for call in audio.call_args_list))

    def test_example_audio_rejects_blank_or_oversized_text_without_download(self):
        with patch.object(services, 'get_audio') as audio:
            for text in ('', '   ', 'x' * 1501):
                with self.subTest(text=text[:10]), self.assertRaises(services.HelperError):
                    services.get_example_audio(text, Path('audio-cache'))
            audio.assert_not_called()

    def test_example_audio_uses_plain_text_and_existing_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(services, 'request_bytes', return_value=(b'ID3' + b'x' * 400, 'audio/mpeg')) as download:
                first = services.get_example_audio('<b>¡Qué</b> bonito es este ejemplo!', Path(directory))
                second = services.get_example_audio('¡Qué bonito es este ejemplo!', Path(directory))
        self.assertEqual(first, second)
        self.assertEqual(download.call_count, 1)

    def test_dictionary_shows_spanish_example_instead_of_english_definition(self):
        response = {'entries': [{'language': {'code': 'es'}, 'senses': [{'definition': 'to save money', 'examples': ['¿Cuánto dinero hemos ahorrado este mes?']}]}]}
        with patch.object(services, 'request_bytes', return_value=(json.dumps(response).encode(), 'application/json')):
            hint = services.dictionary_hint('ahorrar')
        self.assertIn('¿Cuánto', hint['example'])
        self.assertNotIn('to save', str(hint))
        self.assertIn('wiktionary.org', hint['url'])

    def test_dictionary_does_not_fabricate_example_when_absent(self):
        with patch.object(services, 'request_bytes', return_value=(b'{"entries":[]}', 'application/json')):
            with self.assertRaises(services.HelperError):
                services.dictionary_hint('xyz')

    def test_audio_is_cached_without_second_network_request(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(services, 'request_bytes', return_value=(b'ID3' + b'x' * 400, 'audio/mpeg')) as download:
                first = services.get_audio('niño', Path(directory))
                second = services.get_audio('niño', Path(directory))
                self.assertEqual(first, second)
                self.assertEqual(download.call_count, 1)
                self.assertEqual(first.read_bytes()[:3], b'ID3')

    def test_error_html_never_becomes_cached_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(services, 'request_bytes', return_value=(b'<html>' + b'x' * 300, 'text/html')):
                with self.assertRaises(services.HelperError):
                    services.get_audio('hola', Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_slow_and_normal_audio_have_separate_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(services, 'request_bytes', return_value=(b'ID3' + b'x' * 400, 'audio/mpeg')):
                normal = services.get_audio('hola', Path(directory))
                slow = services.get_audio('hola', Path(directory), slow=True)
                self.assertNotEqual(normal, slow)

    def test_network_failures_are_actionable(self):
        with patch.object(services, 'urlopen', side_effect=URLError('offline')):
            with self.assertRaisesRegex(services.HelperError, 'Internet'):
                services.request_bytes('https://example.com')

    def test_auth_error_does_not_echo_secret_or_server_body(self):
        with patch.object(services, 'urlopen', side_effect=HTTPError('https://example.com', 401, 'secret', {}, None)):
            with self.assertRaises(services.HelperError) as captured:
                services.request_bytes('https://example.com')
            self.assertNotIn('secret', str(captured.exception))

    def test_ai_request_is_structured_and_storage_disabled(self):
        expected = {'example': 'Quiero ahorrar dinero para visitar a mi familia este verano.', 'explanation': 'Guardar dinero para usarlo en el futuro.'}
        response = {'output': [{'content': [{'type': 'output_text', 'text': json.dumps(expected)}]}]}
        request = Mock(return_value=(json.dumps(response).encode(), 'application/json'))
        hint = services.ai_hint(core.CardContext('ahorrar', meaning='sparen'), 'test-plan-model', requester=request)
        self.assertEqual(hint['example'], expected['example'])
        payload = request.call_args.args[0]
        self.assertFalse(payload['store'])
        self.assertTrue(payload['text']['format']['strict'])
        self.assertIn('sparen', payload['input'])

    def test_ai_refusal_or_incomplete_json_is_not_displayed_as_hint(self):
        request = Mock(return_value=(b'{"output":[{"content":[{"type":"refusal"}]}]}', 'application/json'))
        with self.assertRaises(services.HelperError):
            services.ai_hint(core.CardContext('hola'), 'test-plan-model', requester=request)


if __name__ == '__main__':
    unittest.main()
