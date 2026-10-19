"""Regression: a correctly detected word must not fail just for lacking examples."""
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

NO_EXAMPLES = json.dumps({'entries': [{'language': {'code': 'es'}, 'senses': [
    {'definition': 'quality, attribute', 'examples': []}]}]}).encode()
SPANISH_PAGE = '''<h2>Portugués</h2><dl><dt>1</dt><dd>Wrong language.</dd></dl>
<h2 id="Español"><span>Español</span></h2><h3>Sustantivo femenino</h3>
<dl><dt>1</dt><dd>Una <a href="/wiki/propiedad">propiedad</a> que distingue a una persona o cosa.</dd></dl>
<h2>Referencias y notas</h2>'''.encode()


class HintFallbackTests(unittest.TestCase):
    def test_reported_word_has_a_local_b1_hint_with_article(self):
        vocabulary = json.loads((ROOT / 'spanish_helper/vocabulary.json').read_text(encoding='utf-8'))
        hint = core.local_hint(core.CardContext('la cualidad'), vocabulary)
        self.assertIsNotNone(hint, 'la cualidad must have an offline B1 hint')
        self.assertIn('cualidad', hint['example'])

    def test_missing_example_falls_back_to_spanish_definition(self):
        with patch.object(services, 'request_bytes', side_effect=[(NO_EXAMPLES, 'application/json'), (SPANISH_PAGE, 'text/html')]):
            hint = services.dictionary_hint('la cualidad')
        self.assertIn('propiedad', hint['explanation'])
        self.assertNotIn('quality', str(hint))
        self.assertNotIn('Wrong language', str(hint))
        self.assertEqual(hint['url'], 'https://es.wiktionary.org/wiki/cualidad')

    def test_primary_dictionary_failure_still_tries_spanish_definition(self):
        with patch.object(services, 'request_bytes', side_effect=[services.HelperError('No entry'), (SPANISH_PAGE, 'text/html')]):
            hint = services.dictionary_hint('otra palabra')
        self.assertIn('propiedad', hint['explanation'])

    def test_english_only_page_never_becomes_a_spanish_hint(self):
        html = b'<h2>English</h2><dl><dt>1</dt><dd>English meaning.</dd></dl>'
        with patch.object(services, 'request_bytes', side_effect=[(NO_EXAMPLES, 'application/json'), (html, 'text/html')]):
            with self.assertRaises(services.HelperError):
                services.dictionary_hint('unknown')


if __name__ == '__main__':
    unittest.main()
