"""Regression checks for the user's audited vocabulary and sense-specific hints."""
import importlib
import json
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
if 'spanish_helper' not in sys.modules:
    package = types.ModuleType('spanish_helper')
    package.__path__ = [str(ROOT / 'spanish_helper')]
    sys.modules['spanish_helper'] = package
core = importlib.import_module('spanish_helper.core')


class DeckHintTests(unittest.TestCase):
    def test_real_deck_field_names_provide_meaning_context(self):
        context = core.extract_context({'question': 'la carrera', 'answer': 'der Studiengang'}, 'la carrera', {})
        self.assertEqual(context.word, 'la carrera')
        self.assertEqual(context.meaning, 'der Studiengang')

    def test_different_senses_of_the_same_word_are_not_mixed(self):
        data = {'la carrera': [
            {'meaning': 'der Studiengang', 'explanation': 'Un programa de estudios universitarios.', 'source': 'fixture'},
            {'meaning': 'das Rennen', 'explanation': 'Una competición para llegar antes que otros.', 'source': 'fixture'}]}
        first = core.local_hint(core.CardContext('la carrera', meaning='der Studiengang'), {}, data)
        second = core.local_hint(core.CardContext('la carrera', meaning='das Rennen'), {}, data)
        self.assertIn('estudios', first['explanation'])
        self.assertIn('competición', second['explanation'])
        self.assertNotIn('meaning', first)

    def test_unrecognized_sense_does_not_use_a_different_recorded_sense(self):
        data = {'el banco': [
            {'meaning': 'die Bank (Geldinstitut)', 'explanation': 'Lugar para guardar dinero.'},
            {'meaning': 'die Bank (Sitzmöbel)', 'explanation': 'Asiento para varias personas.'}]}
        self.assertIsNone(core.local_hint(core.CardContext('el banco', meaning='sand bank'), {}, data))

    def test_single_saved_sense_is_only_used_without_conflicting_meaning(self):
        data = {'la carrera': [{'meaning': 'der Studiengang', 'explanation': 'Estudios universitarios.'}]}
        self.assertIsNone(core.local_hint(core.CardContext('la carrera', meaning='das Rennen'), {}, data))
        self.assertIn('universitarios', core.local_hint(core.CardContext('la carrera'), {}, data)['explanation'])

    def test_every_audited_card_has_a_nonempty_offline_hint(self):
        fixture = ROOT / 'tools/data/audited-vocabulary.json'
        corpus = ROOT / 'spanish_helper/deck_hints.json'
        self.assertTrue(fixture.exists(), 'Full-deck audit fixture must be saved')
        self.assertTrue(corpus.exists(), 'Expanded offline hint corpus must be bundled')
        items = json.loads(fixture.read_text(encoding='utf-8'))
        hints = json.loads(corpus.read_text(encoding='utf-8'))
        vocabulary = json.loads((ROOT / 'spanish_helper/vocabulary.json').read_text(encoding='utf-8'))
        self.assertEqual(sum(item['note_count'] for item in items), 2480)
        failures = []
        for item in items:
            context = core.CardContext(item['word'], meaning=item['meaning'])
            hint = core.local_hint(context, vocabulary, hints)
            if not hint or not (hint.get('example', '').strip() or hint.get('explanation', '').strip()):
                failures.append(item['word'])
        self.assertEqual(failures, [])

    def test_saved_hints_match_common_ambiguous_meanings(self):
        hints = json.loads((ROOT / 'spanish_helper/deck_hints.json').read_text(encoding='utf-8'))
        cases = [('la carrera', 'der Studiengang', 'estudios'),
                 ('el piso', 'das Stockwerk', 'plantas'),
                 ('el piso', 'die Wohnung', 'Vivienda'),
                 ('sonar', 'klingeln', 'teléfono'),
                 ('aburrir', 'langweilen', 'película'),
                 ('la patata', 'Kartoffel', 'cocinarlas')]
        for word, meaning, expected in cases:
            with self.subTest(word=word, meaning=meaning):
                hint = core.local_hint(core.CardContext(word, meaning=meaning), {}, hints)
                self.assertIsNotNone(hint)
                self.assertIn(expected.casefold(), (hint.get('example', '') + hint.get('explanation', '')).casefold())


if __name__ == '__main__':
    unittest.main()
