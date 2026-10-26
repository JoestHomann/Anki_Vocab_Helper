"""Load the add-on against installed Anki/Qt, using a simulated reviewer.

No user collection is opened or changed. Run on Windows with Anki installed.
"""
from concurrent.futures import Future
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ANKI = Path(os.environ['LOCALAPPDATA']) / 'Programs/Anki'
for relative in ('app_packages', 'app_packages/win32', 'app_packages/win32/lib', 'app_packages/pywin32_system32'):
    sys.path.insert(0, str(ANKI / relative))
os.add_dll_directory(str(ANKI))
os.add_dll_directory(str(ANKI / 'app_packages/pywin32_system32'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import aqt
from aqt.qt import QApplication, QMainWindow, QMenu, QDialog, QTimer, QLineEdit, QCheckBox, QPushButton, QDialogButtonBox, QFontDatabase, QFont, QComboBox
from aqt.reviewer import Reviewer
from anki.buildinfo import version

app = QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
app.setFont(QFont('Segoe UI', 9))
window = QMainWindow()
window.form = SimpleNamespace(menuTools=QMenu(window))
window.pm = SimpleNamespace(profileFolder=lambda: str(ROOT / 'output/test-profile-one'))
options = json.loads((ROOT / 'spanish_helper/config.json').read_text())
options['chatgpt_model'] = 'test-plan-model'
def write_config(name, value):
    options.clear(); options.update(value)
window.addonManager = SimpleNamespace(getConfig=lambda name: options.copy(), writeConfig=write_config)
jobs = []
window.taskman = SimpleNamespace(run_in_background=lambda task, done: jobs.append((task, done)))
window.state = 'review'
window.reviewer = Reviewer.__new__(Reviewer)
window.reviewer.state = 'question'
scripts = []
window.reviewer.web = SimpleNamespace(eval=scripts.append, evalWithCallback=lambda js, callback: callback('ahorrar'))
aqt.mw = window

spec = importlib.util.spec_from_file_location('spanish_helper', ROOT / 'spanish_helper/__init__.py', submodule_search_locations=[str(ROOT / 'spanish_helper')])
addon = importlib.util.module_from_spec(spec)
sys.modules['spanish_helper'] = addon
spec.loader.exec_module(addon)

# Never read real ChatGPT sessions in this integration harness.
patch.object(addon.chatgpt, 'accounts', return_value={'active': '', 'accounts': []}).start()


def card(word='ahorrar'):
    return SimpleNamespace(note=lambda: {'Spanish': word, 'Back': 'sparen'})


def click(action):
    message = 'spanish-helper:' + json.dumps({'token': addon.state['token'], 'action': action})
    assert addon.handle_message((False, None), message, window.reviewer) == (True, None)


def finish():
    work, done = jobs.pop(0)
    future = Future()
    try:
        future.set_result(work())
    except Exception as error:
        future.set_exception(error)
    done(future)


assert addon.show_card in aqt.gui_hooks.reviewer_did_show_question._hooks
assert len(window.form.menuTools.actions()) == 1
window.reviewer.card = card()
addon.show_card(window.reviewer.card)
assert addon.state['context'].word == 'ahorrar'
click('hint')
finish()
assert 'Guardar dinero' in scripts[-1]
print('PASS: installed Anki hooks, Qt menu and local hint bridge')

# Exercise the actual field names and a previously ambiguous meaning from this deck.
window.reviewer.web.evalWithCallback = lambda js, callback: callback('el piso')
window.reviewer.card = SimpleNamespace(note=lambda: {'question': 'el piso', 'answer': 'das Stockwerk'})
addon.show_card(window.reviewer.card)
with patch.object(addon, 'dictionary_hint', side_effect=AssertionError('Offline hint attempted a network lookup')):
    click('hint')
    finish()
assert 'plantas' in scripts[-1]
window.reviewer.web.evalWithCallback = lambda js, callback: callback('ahorrar')
addon.show_card(card())
print('PASS: real vocabulary fields resolve the correct offline meaning without dictionary access')

with patch.object(addon, 'get_audio', return_value=ROOT / 'output/test.mp3'), patch.object(addon.av_player, 'play_file') as play:
    click('pronounce')
    addon.show_card(card('aprovechar'))
    finish()
    assert play.call_count == 0
    click('pronounce')
    finish()
    assert play.call_count == 1
print('PASS: old-card audio is ignored; current-card audio reaches Anki player')

# The example speaker reads the delivered hint, never the selected/card word.
addon.show_card(card())
before = len(jobs)
click('example_audio')
assert len(jobs) == before and 'Muestra primero' in scripts[-1]
click('hint')
finish()
example = addon.state['hint_example']
assert example and example != 'ahorrar'
audio_paths = [ROOT / 'output/first.mp3', ROOT / 'output/second.mp3']
with patch.object(addon, 'get_example_audio', return_value=audio_paths) as get_example, patch.object(addon.av_player, 'play_tags') as play:
    message = 'spanish-helper:' + json.dumps({'token': addon.state['token'], 'action': 'example_audio', 'selection': 'wrong selection', 'selectionOnCard': True, 'text': 'untrusted text'})
    addon.handle_message((False, None), message, window.reviewer)
    click('example_audio')
    assert len(jobs) == 1
    finish()
    assert get_example.call_args.args[0] == example
    assert [tag.filename for tag in play.call_args.args[0]] == [str(path) for path in audio_paths]
    assert 'example_audio' in scripts[-1] and 'example_audio' not in addon.state['busy']
    click('example_audio')
    addon.show_card(card('otro'))
    finish()
    assert play.call_count == 1
    # Replacing a hint on the same card also invalidates old example audio.
    addon.state['hint_example'] = example
    click('example_audio')
    click('hint')
    finish()
    assert play.call_count == 1
    finish()
options['online_audio'] = False
options['slow_audio'] = True
with patch.object(addon.av_player, 'players', [SimpleNamespace(rank_for_tag=lambda tag: 1)]), patch.object(addon.av_player, 'play_tags') as play:
    click('example_audio')
    tag = play.call_args.args[0][0]
    assert tag.field_text == addon.state['hint_example'] and tag.speed == 0.8
options['online_audio'] = True
options['slow_audio'] = False
print('PASS: full hint example audio, trusted text, ordered segments, offline voice, duplicate clicks and stale replies')

before = len(jobs)
addon.handle_message((False, None), 'spanish-helper:{"token":"old","action":"hint"}', window.reviewer)
assert len(jobs) == before
addon.state_changed('deckBrowser', 'review')
assert not addon.state['token'] and addon.state['context'] is None
print('PASS: stale bridge commands and leaving review')

window.state = 'deckBrowser'
QTimer.singleShot(0, lambda: next(w for w in app.topLevelWidgets() if isinstance(w, QDialog)).accept())
addon.settings()
print('PASS: real Qt settings dialog opens and saves')

# Checking is explicit, independent of selected text, cached, and answer-side only.
window.state = 'review'
window.reviewer.state = 'question'
window.reviewer.card = card('embarazada')
addon.show_card(window.reviewer.card)
before = len(jobs)
click('check')
assert len(jobs) == before and 'Muestra primero' in scripts[-1]
window.reviewer.state = 'answer'
window.reviewer.web.evalWithCallback = lambda js, callback: callback('embarazada sparen')
addon.show_card(window.reviewer.card)
checked = {'verdict': 'incorrect', 'explanation': 'No es una traducción válida.', 'suggestion': 'schwanger', 'saved': 'sparen', 'source': 'test'}
with patch.object(addon, 'check_translation', return_value=checked) as checker:
    message = 'spanish-helper:' + json.dumps({'token': addon.state['token'], 'action': 'check', 'selection': 'other text', 'selectionOnCard': True})
    addon.handle_message((False, None), message, window.reviewer)
    # Double-clicking while a job is outstanding must not create a second request.
    click('check')
    assert len(jobs) == 1
    finish()
    assert checker.call_args.args[0].word == 'embarazada'
    assert checker.call_args.args[0].meaning == 'sparen'
    assert 'incorrect' in scripts[-1] and 'schwanger' in scripts[-1]
    click('check')
    finish()
    assert checker.call_count == 1
    # Editing the saved translation invalidates the previous pair's cache.
    window.reviewer.card = SimpleNamespace(note=lambda: {'Spanish': 'embarazada', 'Back': 'schwanger'})
    addon.show_card(window.reviewer.card)
    click('check')
    finish()
    assert checker.call_count == 2
    # A late check response must not reach the next card or enter the cache.
    window.reviewer.card = card('nuevo')
    addon.show_card(window.reviewer.card)
    click('check')
    window.reviewer.card = card('otro')
    addon.show_card(window.reviewer.card)
    before = len(scripts)
    finish()
    assert len(scripts) == before
print('PASS: answer-only translation check, saved pair, duplicate clicks, caching, edits and stale replies')

addon.check_cache.clear()
addon.show_card(window.reviewer.card)
with patch.object(addon.chatgpt, 'response', side_effect=addon.chatgpt.AuthError(
        'Abre Herramientas → Spanish Helper y pulsa Continue with ChatGPT.')):
    click('check')
    finish()
assert 'Continue with ChatGPT' in scripts[-1]
print('PASS: disconnected account gives subscription sign-in guidance')

addon.hint_cache['test'] = {'example': 'cached'}
addon.profile_closed()
assert not addon.check_cache and not addon.hint_cache and not addon.state['token']
print('PASS: profile close clears caches and review state')


def run_settings(edit, save=True):
    def interact():
        dialog = next(w for w in app.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible())
        edit(dialog)
        button = QDialogButtonBox.StandardButton.Save if save else QDialogButtonBox.StandardButton.Cancel
        dialog.findChild(QDialogButtonBox).button(button).click()
    QTimer.singleShot(0, interact)
    addon.settings()


window.state = 'deckBrowser'
context = addon.extract_context({'Spanish':'hola','Back':'Hallo'}, 'hola', options)
# Stale API settings and environment keys cannot switch the transport or model.
options.update(ai_provider='api_key', model='old-api-model', check_model='old-check-model', remember_api_key=True)
assert set(addon.config()) == set(addon.DEFAULTS)
with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-unused-key'}), patch.object(addon.chatgpt, 'response', return_value=(json.dumps({'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps({'verdict':'correct','explanation':'Es una traducción válida.','suggestion':''})}]}]}).encode(), 'application/json')) as plan, patch.object(addon, 'get_audio', side_effect=AssertionError('Unexpected public request')):
    result = addon.ai_request(addon.check_translation, context, addon.config())
    assert 'Using ChatGPT plan' in result['source']
    assert plan.call_args.args[1]['model'] == 'test-plan-model'
    assert 'synthetic-unused-key' not in str(plan.call_args)
with patch.object(addon.chatgpt, 'response', side_effect=addon.chatgpt.AuthError('Plan limit')):
    try:
        addon.ai_request(addon.check_translation, context, addon.config())
        raise AssertionError('Plan error was suppressed')
    except addon.HelperError as error:
        assert 'Plan limit' in str(error)
assert not hasattr(addon, 'api_key') and not hasattr(addon, 'credentials')
print('PASS: legacy API settings and environment keys cannot enable API access; subscription errors remain errors')

def inspect_subscription_settings(dialog):
    assert dialog.findChild(QLineEdit, 'apiKey') is None
    assert dialog.findChild(QCheckBox, 'rememberApiKey') is None
    assert dialog.findChild(QComboBox, 'aiProvider') is None
    assert len(dialog.findChildren(QLineEdit)) == 4  # Field mappings only.
    assert any(button.text() == 'Continue with ChatGPT' for button in dialog.findChildren(QPushButton))
    button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save)
    assert button.isVisible()
    (ROOT / 'output/screenshots').mkdir(parents=True, exist_ok=True)
    dialog.grab().save(str(ROOT / 'output/screenshots/chatgpt-settings.png'))

original_options = options.copy()
run_settings(inspect_subscription_settings, save=False)
assert options == original_options
run_settings(inspect_subscription_settings)
assert set(options) == set(addon.DEFAULTS)
assert 'ai_provider' not in options and 'remember_api_key' not in options
print('PASS: subscription-only settings, cancel, save, obsolete settings cleanup and visible Save button')
print('Anki runtime:', version)
