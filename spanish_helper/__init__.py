"""Spanish Helper: a review overlay for Anki desktop."""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4
from dataclasses import replace

from aqt import mw, gui_hooks
from aqt.reviewer import Reviewer
from aqt.qt import (QAction, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                    QLabel, QLineEdit, QVBoxLayout)
from aqt.sound import av_player
from anki.sound import TTSTag

from .core import extract_context, is_current, local_hint, plain_text
from .services import HelperError, ai_hint, dictionary_hint, get_audio

ROOT = Path(__file__).parent
VOCABULARY = json.loads((ROOT / 'vocabulary.json').read_text(encoding='utf-8'))
DECK_HINTS = json.loads((ROOT / 'deck_hints.json').read_text(encoding='utf-8')) if (ROOT / 'deck_hints.json').exists() else {}
DEFAULTS = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
CSS = (ROOT / 'web' / 'overlay.css').read_text(encoding='utf-8')
JS = (ROOT / 'web' / 'overlay.js').read_text(encoding='utf-8')
state = {'token': '', 'context': None, 'key': '', 'busy': set()}
hint_cache = {}


def config():
    return {**DEFAULTS, **(mw.addonManager.getConfig(__name__) or {})}


def send(event, **values):
    if mw.state == 'review' and mw.reviewer:
        payload = json.dumps({'event': event, 'token': state['token'], **values}, ensure_ascii=True)
        mw.reviewer.web.eval('window.SpanishHelper && window.SpanishHelper.receive(' + payload + ');')


def show_card(card):
    state['token'] = uuid4().hex
    state['context'] = None
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
        payload = json.dumps({'token': token, 'word': context.word}, ensure_ascii=True)
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
        if action not in ('pronounce', 'hint') or action in state['busy']:
            return (True, None)
        selected = plain_text(str(request.get('selection', '')))
        # Only allow vocabulary actually present on the displayed card.
        card_context = state['context']
        if selected and len(selected) <= 180 and request.get('selectionOnCard') is True:
            card_context = replace(card_context, word=selected, example='', explanation='', meaning='')
        if not card_context.word:
            send('error', action=action, message='Selecciona una palabra de la tarjeta o configura el campo en Herramientas → Spanish Helper.')
            return (True, None)
        options = config()
        if action == 'pronounce' and not options['online_audio']:
            tag = TTSTag(card_context.word, 'es_ES', [], 0.8 if options['slow_audio'] else 1.0, [])
            if not any(player.rank_for_tag(tag) is not None for player in av_player.players):
                raise HelperError('No hay una voz española instalada. Activa el audio por Internet en Herramientas → Spanish Helper o instala una voz española de Windows.')
            av_player.play_tags([tag])
            send('audio', word=card_context.word)
            return (True, None)
        state['busy'].add(action)
        key = state['key'] or os.environ.get('OPENAI_API_KEY', '')
        cache_key = (card_context, options['ai_hints'], options['model'])

        def work():
            if action == 'pronounce':
                return get_audio(card_context.word, ROOT / 'user_files' / 'audio', options['slow_audio'])
            saved = local_hint(card_context, VOCABULARY, DECK_HINTS)
            if saved:
                return saved
            if cache_key in hint_cache:
                return hint_cache[cache_key]
            if options['ai_hints']:
                if not key:
                    raise HelperError('Añade tu clave de OpenAI en Herramientas → Spanish Helper, o desactiva las pistas con IA para usar el diccionario.')
                return ai_hint(card_context, key, options['model'])
            if options['online_dictionary']:
                return dictionary_hint(card_context.word)
            raise HelperError('No hay una pista local. Añade un campo «Ejemplo» o activa el diccionario o la IA en Herramientas → Spanish Helper.')

        def done(future):
            try:
                result = future.result()
            except Exception as error:
                if is_current(token, state['token'], mw.state == 'review'):
                    state['busy'].discard(action)
                    send('error', action=action, message=str(error) if isinstance(error, HelperError) else 'No se puede completar la acción. Vuelve a intentarlo.')
                return
            if not is_current(token, state['token'], mw.state == 'review'):
                return
            state['busy'].discard(action)
            if action == 'pronounce':
                av_player.play_file(str(result))
                send('audio', word=card_context.word)
            else:
                if len(hint_cache) > 250:
                    hint_cache.clear()
                hint_cache[cache_key] = result
                send('hint', word=card_context.word, **result)

        mw.taskman.run_in_background(work, done)
    except (ValueError, KeyError, TypeError):
        pass
    except HelperError as error:
        send('error', action='pronounce', message=str(error))
    return (True, None)


def state_changed(new_state, old_state):
    if new_state != 'review':
        state['token'] = ''
        state['context'] = None
        state['busy'].clear()


def settings():
    options = config()
    dialog = QDialog(mw)
    dialog.setWindowTitle('Spanish Helper · Ajustes')
    dialog.setMinimumWidth(510)
    layout = QVBoxLayout(dialog)
    intro = QLabel('Dos botones para practicar español. Las pistas locales son de nivel B1.\nSelecciona texto en una tarjeta para practicar solo esa palabra.')
    intro.setWordWrap(True)
    layout.addWidget(intro)
    form = QFormLayout()
    layout.addLayout(form)
    checks = {}
    for name, label in [('enabled', 'Mostrar el ayudante'), ('online_audio', 'Pronunciación por Internet (Google)'),
                        ('slow_audio', 'Pronunciación lenta'), ('online_dictionary', 'Ejemplos del diccionario (nivel variable)'),
                        ('ai_hints', 'Generar pistas B1 con OpenAI (requiere clave)')]:
        box = QCheckBox(label)
        box.setChecked(bool(options[name]))
        form.addRow(box)
        checks[name] = box
    edits = {}
    for name, label in [('word_field', 'Campo español (vacío = automático)'), ('example_field', 'Campo de ejemplo (opcional)'),
                        ('hint_field', 'Campo de pista (opcional)'), ('model', 'Modelo de OpenAI')]:
        edit = QLineEdit(str(options[name]))
        form.addRow(label, edit)
        edits[name] = edit
    key = QLineEdit(state['key'])
    key.setEchoMode(QLineEdit.EchoMode.Password)
    key.setPlaceholderText('Solo para esta sesión; o usa OPENAI_API_KEY')
    form.addRow('Clave de OpenAI', key)
    privacy = QLabel('Al pulsar un botón, el texto elegido se envía al servicio activado.\nLa IA recibe también el significado de la tarjeta para elegir el sentido correcto.\nLa clave introducida aquí no se guarda en disco. El audio se guarda localmente.\nLos ejemplos del diccionario proceden de Wiktionary (CC BY-SA).')
    privacy.setWordWrap(True)
    layout.addWidget(privacy)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec():
        options.update({name: box.isChecked() for name, box in checks.items()})
        options.update({name: edit.text().strip() for name, edit in edits.items()})
        options['model'] = options['model'] or DEFAULTS['model']
        state['key'] = key.text().strip()
        mw.addonManager.writeConfig(__name__, options)
        hint_cache.clear()
        if mw.state == 'review' and mw.reviewer.card:
            show_card(mw.reviewer.card)


def profile_closed():
    state['key'] = ''
    hint_cache.clear()
    state_changed('deckBrowser', 'review')


menu_action = QAction('Spanish Helper…', mw)
menu_action.triggered.connect(settings)
mw.form.menuTools.addAction(menu_action)
gui_hooks.reviewer_did_show_question.append(show_card)
gui_hooks.reviewer_did_show_answer.append(show_card)
gui_hooks.webview_did_receive_js_message.append(handle_message)
gui_hooks.state_did_change.append(state_changed)
gui_hooks.profile_will_close.append(profile_closed)
