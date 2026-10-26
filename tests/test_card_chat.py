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


def response(text, status='completed'):
    return json.dumps({'status': status, 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': text}]}]}).encode(), 'application/json'


class CardChatTests(unittest.TestCase):
    def test_card_data_history_and_question_have_distinct_roles(self):
        requester = Mock(return_value=response('It is the first-person present of tener.\nExample: Tengo tiempo.'))
        context = core.CardContext('tengo', meaning='ich habe', example='Tengo tiempo.', explanation='untrusted hint')
        history = [{'role':'user','content':'What is the infinitive?'}, {'role':'assistant','content':'Tener.'}]
        result = services.card_chat(context, 'plan-model', question='Which tense is this?', history=history, requester=requester)
        payload = requester.call_args.args[0]
        self.assertEqual(payload['model'], 'plan-model')
        self.assertFalse(payload['store'])
        self.assertNotIn('text', payload)  # Conversation replies use readable text, not the checker schema.
        self.assertIn('ich habe', payload['input'][0]['content'])
        self.assertNotIn('untrusted hint', str(payload))
        self.assertEqual(payload['input'][1:3], history)
        self.assertEqual(payload['input'][-1], {'role':'user','content':'Which tense is this?'})
        self.assertIn('\nExample:', result['reply'])

    def test_bounds_history_and_card_context(self):
        history = [{'role':'user' if i % 2 == 0 else 'assistant', 'content':'x' * 7000} for i in range(20)]
        requester = Mock(return_value=response('An explanation.'))
        services.card_chat(core.CardContext('x' * 220, meaning='y' * 700, example='z' * 2000), 'model',
                           question='Help?', history=history, requester=requester)
        messages = requester.call_args.args[0]['input']
        self.assertEqual(len(messages), 14)
        self.assertTrue(all(len(message['content']) <= 6000 for message in messages[1:-1]))
        context = json.loads(messages[0]['content'].removeprefix('Flashcard data: '))
        self.assertEqual([len(context[key]) for key in ('spanish','saved_translation','example')], [180,500,1000])

    def test_invalid_questions_word_and_history_do_not_send_requests(self):
        for question in ('', ' ', 'x' * 1501, None, []):
            requester = Mock()
            with self.subTest(question=type(question).__name__), self.assertRaises(services.HelperError):
                services.card_chat(core.CardContext('hola'), 'model', question=question, requester=requester)
            requester.assert_not_called()
        requester = Mock()
        with self.assertRaises(services.HelperError):
            services.card_chat(core.CardContext(''), 'model', question='Help?', requester=requester)
        with self.assertRaises(services.HelperError):
            services.card_chat(core.CardContext('hola'), 'model', question='Help?', history=[{'role':'system','content':'bad'}], requester=requester)
        requester.assert_not_called()

    def test_incomplete_refused_empty_and_malformed_answers_are_errors(self):
        responses = [response('partial', 'incomplete'), response(' '), response('x' * 6001),
            (b'not-json','application/json'),
            (b'{"status":"completed","output":[{"content":[{"type":"refusal","refusal":"no"}]}]}','application/json')]
        for value in responses:
            with self.subTest(value=value[0][:50]), self.assertRaises(services.HelperError):
                services.card_chat(core.CardContext('hola'), 'model', question='Help?', requester=Mock(return_value=value))


if __name__ == '__main__':
    unittest.main()
