"""Spanish Helper: a review overlay for Anki desktop."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
from dataclasses import replace

from aqt import mw, gui_hooks
from aqt.reviewer import Reviewer
from aqt.qt import (QAction, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)
from aqt.utils import showInfo
from aqt.sound import av_player
from anki.sound import SoundOrVideoTag, TTSTag

from .core import extract_context, is_current, local_hint, plain_text
from . import chatgpt
from .services import HelperError, ai_hint, check_translation, dictionary_hint, get_audio, get_example_audio

ROOT = Path(__file__).parent
VOCABULARY = json.loads((ROOT / 'vocabulary.json').read_text(encoding='utf-8'))
DECK_HINTS = json.loads((ROOT / 'deck_hints.json').read_text(encoding='utf-8')) if (ROOT / 'deck_hints.json').exists() else {}
DEFAULTS = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
CSS = (ROOT / 'web' / 'overlay.css').read_text(encoding='utf-8')
JS = (ROOT / 'web' / 'overlay.js').read_text(encoding='utf-8')
state = {'token': '', 'context': None, 'busy': set(), 'hint_example': ''}
hint_cache = {}
check_cache = {}


def config():
    saved = mw.addonManager.getConfig(__name__) or {}
    # Old provider/key/model options cannot re-enable removed authentication routes.
    return {name: saved.get(name, default) for name, default in DEFAULTS.items()}


def send(event, **values):
    if mw.state == 'review' and mw.reviewer:
        payload = json.dumps({'event': event, 'token': state['token'], **values}, ensure_ascii=True)
        mw.reviewer.web.eval('window.SpanishHelper && window.SpanishHelper.receive(' + payload + ');')


def ai_request(function, context, options):
    profile = mw.pm.profileFolder()
    try:
        model = options['chatgpt_model']
        if not model:
            choices = chatgpt.models(profile)
            model = next((item['slug'] for item in choices if 'luna' in item['slug']), choices[0]['slug'])
        result = function(context, model, requester=lambda payload: chatgpt.response(profile, payload))
        result['source'] = result.get('source', '') + ' · Using ChatGPT plan'
        return result
    except chatgpt.AuthError as error:
        raise HelperError(str(error)) from None


def show_card(card):
    state['token'] = uuid4().hex
    state['context'] = None
    state['hint_example'] = ''
    state['busy'].clear()
    options = config()
    web = mw.reviewer.web
    if not options['enabled']:
        web.eval('window.SpanishHelper && window.SpanishHelper.destroy();')
        return
    # Read only rendered, visible card text; hidden answer content is excluded in JS.
    token = state['token']
    fields = dict(card.note().items())

    def got_visible(text):
        if not is_current(token, state['token'], mw.state == 'review'):
            return
        context = extract_context(fields, str(text or ''), options)
        state['context'] = context
        payload = json.dumps({'token': token, 'word': context.word,
                              'usingChatGPT': True,
                              'answerShown': getattr(mw.reviewer, 'state', '') == 'answer'}, ensure_ascii=True)
        web.eval(JS + '\nwindow.SpanishHelper.mount(' + payload + ',' + json.dumps(CSS) + ');')

    web.evalWithCallback("document.getElementById('qa')?.innerText || ''", got_visible)


def handle_message(handled, message, context):
    if handled[0] or not message.startswith('spanish-helper:') or not isinstance(context, Reviewer):
        return handled
    try:
        request = json.loads(message[len('spanish-helper:'):])
        token, action = request['token'], request['action']
        if not is_current(token, state['token'], mw.state == 'review') or state['context'] is None:
            return (True, None)
        if action not in ('pronounce', 'example_audio', 'hint', 'check') or action in state['busy']:
            return (True, None)
        if action in ('pronounce', 'example_audio') and state['busy'].intersection(('pronounce', 'example_audio')):
            return (True, None)
        if action == 'check' and getattr(mw.reviewer, 'state', '') != 'answer':
            send('error', action=action, message='Muestra primero la respuesta para comprobar tu traducción sin adelantarla.')
            return (True, None)
        selected = plain_text(str(request.get('selection', '')))
        # Only allow vocabulary actually present on the displayed card.
        card_context = state['context']
        if action not in ('check', 'example_audio') and selected and len(selected) <= 180 and request.get('selectionOnCard') is True:
            card_context = replace(card_context, word=selected, example='', explanation='', meaning='')
        speech_text = state['hint_example'] if action == 'example_audio' else card_context.word
        if action == 'example_audio' and not speech_text:
            raise HelperError('Muestra primero una pista con un ejemplo para escucharlo.')
        if action == 'example_audio' and len(speech_text) > 1500:
            raise HelperError('Este ejemplo es demasiado largo para escucharlo (máximo 1500 caracteres).')
        if not card_context.word:
            send('error', action=action, message='Selecciona una palabra de la tarjeta o configura el campo en Herramientas → Spanish Helper.')
            return (True, None)
        options = config()
        if action in ('pronounce', 'example_audio') and not options['online_audio']:
            tag = TTSTag(speech_text, 'es_ES', [], 0.8 if options['slow_audio'] else 1.0, [])
            if not any(player.rank_for_tag(tag) is not None for player in av_player.players):
                raise HelperError('No hay una voz española instalada. Activa el audio por Internet en Herramientas → Spanish Helper o instala una voz española de Windows.')
            av_player.play_tags([tag])
            send('audio', action=action, word=speech_text)
            return (True, None)
        if action == 'hint':
            state['hint_example'] = ''
            state['busy'].discard('example_audio')
        state['busy'].add(action)
        cache_key = (card_context, options['ai_hints'], options['chatgpt_model'])
        check_key = (card_context.word, card_context.meaning, card_context.example, options['chatgpt_model'])

        def work():
            if action == 'check':
                if check_key in check_cache:
                    return check_cache[check_key]
                return ai_request(check_translation, card_context, options)
            if action == 'pronounce':
                return get_audio(card_context.word, ROOT / 'user_files' / 'audio', options['slow_audio'])
            if action == 'example_audio':
                return get_example_audio(speech_text, ROOT / 'user_files' / 'audio', options['slow_audio'])
            saved = local_hint(card_context, VOCABULARY, DECK_HINTS)
            if saved:
                return saved
            if cache_key in hint_cache:
                return hint_cache[cache_key]
            if options['ai_hints']:
                return ai_request(ai_hint, card_context, options)
            if options['online_dictionary']:
                return dictionary_hint(card_context.word)
            raise HelperError('No hay una pista local. Añade un campo «Ejemplo» o activa el diccionario o la IA en Herramientas → Spanish Helper.')

        def still_current():
            return is_current(token, state['token'], mw.state == 'review') and (
                action != 'example_audio' or state['hint_example'] == speech_text)

        def done(future):
            try:
                result = future.result()
            except Exception as error:
                if still_current():
                    state['busy'].discard(action)
                    send('error', action=action, message=str(error) if isinstance(error, HelperError) else 'No se puede completar la acción. Vuelve a intentarlo.')
                return
            if not still_current():
                return
            state['busy'].discard(action)
            if action == 'pronounce':
                av_player.play_file(str(result))
                send('audio', action=action, word=card_context.word)
            elif action == 'example_audio':
                av_player.play_tags([SoundOrVideoTag(str(path)) for path in result])
                send('audio', action=action, word=speech_text)
            elif action == 'check':
                if len(check_cache) >= 250:
                    check_cache.clear()
                check_cache[check_key] = result
                send('check', word=card_context.word, **result)
            else:
                if len(hint_cache) > 250:
                    hint_cache.clear()
                hint_cache[cache_key] = result
                state['hint_example'] = plain_text(result.get('example', ''))
                send('hint', word=card_context.word, **result)

        mw.taskman.run_in_background(work, done)
    except (ValueError, KeyError, TypeError):
        pass
    except HelperError as error:
        send('error', action=locals().get('action', 'pronounce'), message=str(error))
    return (True, None)


def state_changed(new_state, old_state):
    if new_state != 'review':
        state['token'] = ''
        state['context'] = None
        state['hint_example'] = ''
        state['busy'].clear()


def settings():
    options = config()
    dialog = QDialog(mw)
    dialog.setWindowTitle('Spanish Helper · Ajustes')
    dialog.setMinimumWidth(510)
    outer = QVBoxLayout(dialog)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    layout = QVBoxLayout(content)
    scroll.setWidget(content)
    outer.addWidget(scroll)
    available = dialog.screen().availableGeometry()
    dialog.resize(min(740, available.width() - 50), min(780, available.height() - 70))
    intro = QLabel('Pronunciación, pistas y revisión de traducciones.\nLa comprobación con IA se ejecuta solo al pulsar Comprobar, después de mostrar la respuesta.')
    intro.setWordWrap(True)
    layout.addWidget(intro)
    form = QFormLayout()
    layout.addLayout(form)
    checks = {}
    for name, label in [('enabled', 'Mostrar el ayudante'), ('online_audio', 'Pronunciación por Internet (Google)'),
                        ('slow_audio', 'Pronunciación lenta'), ('online_dictionary', 'Ejemplos del diccionario (nivel variable)'),
                        ('ai_hints', 'Generar pistas B1 cuando no hay pista local')]:
        box = QCheckBox(label)
        box.setChecked(bool(options[name]))
        form.addRow(box)
        checks[name] = box
    edits = {}
    profile = mw.pm.profileFolder()
    account_picker, model_picker = QComboBox(), QComboBox()
    model_picker.setObjectName('chatgptModel')
    model_picker.addItem('Automático: modelo disponible del plan', options['chatgpt_model'])
    account_picker.addItem('Añadir una cuenta', '')
    auth_status = QLabel('Conecta tu cuenta para usar tu suscripción de ChatGPT.')
    auth_status.setWordWrap(True)
    try:
        saved = chatgpt.accounts(profile)
        for account in saved['accounts']:
            account_picker.addItem(account['label'] + ' · ' + account['client_id'][-6:], account['client_id'])
        index = account_picker.findData(saved['active'])
        account_picker.setCurrentIndex(max(index, 0))
        if saved['active']:
            auth_status.setText('Using ChatGPT plan · Reanuda la sesión automáticamente.')
    except (chatgpt.AuthError, OSError):
        auth_status.setText('Conecta ChatGPT para usar tu plan. Disponible en Windows.')
    form.addRow('Cuenta ChatGPT', account_picker)
    form.addRow('Modelo del plan', model_picker)
    auth_row = QHBoxLayout()
    connect = QPushButton('Continue with ChatGPT')
    disconnect = QPushButton('Cerrar sesión')
    manage = QPushButton('Manage usage')
    for button in (connect, disconnect, manage):
        auth_row.addWidget(button)
    form.addRow(auth_row)
    form.addRow(auth_status)
    def load_models():
        return chatgpt.models(profile)
    def fill_models(choices):
        previous = model_picker.currentData()
        model_picker.clear()
        model_picker.addItem('Automático: modelo disponible del plan', '')
        for choice in choices:
            model_picker.addItem(choice['display_name'], choice['slug'])
        index = model_picker.findData(previous)
        model_picker.setCurrentIndex(max(index, 0))
    def auth_job(work, done):
        connect.setEnabled(False); disconnect.setEnabled(False)
        auth_status.setText('Un momento… Completa el inicio de sesión en tu navegador si se abre.')
        def complete(future):
            connect.setEnabled(True); disconnect.setEnabled(True)
            hint_cache.clear(); check_cache.clear()
            if not dialog.isVisible():
                return
            try:
                done(future.result())
            except Exception as error:
                auth_status.setText(str(error) if isinstance(error, chatgpt.AuthError) else 'No se pudo completar la conexión. Inténtalo de nuevo.')
        mw.taskman.run_in_background(work, complete)
    def connected(result):
        auth_status.setText('Using ChatGPT plan · ' + result['identity']['label'])
        account_picker.blockSignals(True)
        account_picker.clear(); account_picker.addItem('Añadir una cuenta', '')
        saved = chatgpt.accounts(profile)
        for account in saved['accounts']:
            account_picker.addItem(account['label'] + ' · ' + account['client_id'][-6:], account['client_id'])
        account_picker.setCurrentIndex(max(0, account_picker.findData(saved['active'])))
        account_picker.blockSignals(False)
        fill_models(result['models'])
        if result['identity']['first']:
            showInfo('You’re using your ChatGPT plan.\nLas solicitudes de IA usan los límites de tu plan. Puedes gestionar el uso en los ajustes de ChatGPT.', parent=dialog)
    def start_sign_in():
        selected = account_picker.currentData() or ''
        def work():
            identity = chatgpt.sign_in(profile, selected)
            return {'identity': identity, 'models': load_models()}
        auth_job(work, connected)
    def choose_account():
        selected = account_picker.currentData()
        if not selected:
            return
        def work():
            chatgpt.select_account(profile, selected)
            return load_models()
        def done(choices):
            fill_models(choices); auth_status.setText('Using ChatGPT plan · ' + account_picker.currentText())
        auth_job(work, done)
    connect.clicked.connect(start_sign_in)
    account_picker.currentIndexChanged.connect(choose_account)
    def disconnected(confirmed):
        auth_status.setText('Sesión cerrada.' if confirmed else 'Sesión local cerrada; la revocación remota no se confirmó. Desconecta la aplicación en los ajustes de ChatGPT.')
    disconnect.clicked.connect(lambda: auth_job(lambda: chatgpt.sign_out(profile), disconnected))
    manage.clicked.connect(lambda: __import__('webbrowser').open(chatgpt.USAGE_URL))
    for name, label in [('word_field', 'Campo español (vacío = automático)'),
                        ('translation_field', 'Campo de traducción (vacío = automático)'),
                        ('example_field', 'Campo de ejemplo (opcional)'), ('hint_field', 'Campo de pista (opcional)')]:
        edit = QLineEdit(str(options[name]))
        form.addRow(label, edit)
        edits[name] = edit
    privacy = QLabel('Comprobar envía a OpenAI la palabra, tu traducción y el ejemplo.\nLas solicitudes de IA usan tu suscripción de ChatGPT y están sujetas a sus límites.\nLa conexión se recuerda de forma segura con Windows.\nNo se guardan secretos en la configuración ni se sincronizan con Anki. La revisión no modifica tus tarjetas.')
    privacy.setWordWrap(True)
    layout.addWidget(privacy)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    outer.addWidget(buttons)
    if dialog.exec():
        options.update({name: box.isChecked() for name, box in checks.items()})
        options.update({name: edit.text().strip() for name, edit in edits.items()})
        options['chatgpt_model'] = model_picker.currentData() or ''
        mw.addonManager.writeConfig(__name__, options)
        hint_cache.clear()
        check_cache.clear()
        if mw.state == 'review' and mw.reviewer.card:
            show_card(mw.reviewer.card)


def profile_closed():
    hint_cache.clear()
    check_cache.clear()
    state_changed('deckBrowser', 'review')


menu_action = QAction('Spanish Helper…', mw)
menu_action.triggered.connect(settings)
mw.form.menuTools.addAction(menu_action)
gui_hooks.reviewer_did_show_question.append(show_card)
gui_hooks.reviewer_did_show_answer.append(show_card)
gui_hooks.webview_did_receive_js_message.append(handle_message)
gui_hooks.state_did_change.append(state_changed)
gui_hooks.profile_will_close.append(profile_closed)
