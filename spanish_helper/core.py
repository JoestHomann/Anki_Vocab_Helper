"""Card extraction and local hints, independent of Anki and Qt."""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re
import unicodedata


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('br', 'div', 'p', 'li', 'hr'):
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        if tag in ('div', 'p', 'li'):
            self.parts.append(' ')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value: str) -> str:
    parser = _Text()
    parser.feed(str(value))
    text = ''.join(parser.parts)
    text = re.sub(r'\[sound:[^\]]*\]|\[anki:[^\]]*\]', '', text)
    text = re.sub(r'\{\{c\d+::(.*?)(?:::[^{}]*)?\}\}', r'\1', text)
    return re.sub(r'\s+', ' ', text).strip()


def normalize(value: str) -> str:
    return unicodedata.normalize('NFC', plain_text(value)).casefold().strip(' .!?¿¡')


def lookup_word(word: str) -> str:
    return re.sub(r'^(?:el|la|los|las|un|una)\s+', '', normalize(word))


def first_field(fields: dict[str, str], names: list[str]) -> str:
    by_name = {normalize(k): plain_text(v) for k, v in fields.items()}
    return next((by_name[normalize(n)] for n in names if by_name.get(normalize(n))), '')


@dataclass(frozen=True)
class CardContext:
    word: str
    example: str = ''
    explanation: str = ''
    meaning: str = ''


def extract_context(fields: dict[str, str], visible_text: str, config: dict) -> CardContext:
    """Explicit mapping wins. Otherwise use a Spanish field visible on this side.

    Never silently take a Spanish answer from the hidden side of a reverse card.
    """
    visible = plain_text(visible_text)
    explicit = config.get('word_field', '').strip()
    if explicit:
        word = first_field(fields, [explicit])
    else:
        word = ''
        for name in ('Spanish', 'Español', 'Espanol', 'Palabra', 'Expression', 'Word', 'Vocabulario', 'Front', 'Anverso', 'question', 'Vorderseite'):
            candidate = first_field(fields, [name])
            if candidate and normalize(candidate) in normalize(visible):
                word = candidate
                break
        # Plain vocabulary cards without named fields. Long prompts require selection/mapping.
        if not word and len(visible) <= 140 and len(visible.split()) <= 12:
            word = visible
    return CardContext(
        word=word[:180],
        example=first_field(fields, [config.get('example_field', ''), 'Example', 'Ejemplo', 'Example Sentence', 'Frase', 'Sentence', 'Beispielsatz']),
        explanation=first_field(fields, [config.get('hint_field', ''), 'Hint', 'Pista', 'Explicación', 'Explicacion', 'Definición', 'Definicion']),
        meaning=first_field(fields, [config['translation_field']]) if config.get('translation_field', '').strip() else first_field(
            fields, ['Meaning', 'Translation', 'Traducción', 'Traduccion', 'Bedeutung', 'Übersetzung', 'Back', 'Reverso', 'answer', 'Rückseite']),
    )


def local_hint(context: CardContext, vocabulary: dict, deck_hints: dict | None = None) -> dict | None:
    if context.example or context.explanation:
        return {'example': context.example, 'explanation': context.explanation, 'source': 'Tu tarjeta'}
    if deck_hints:
        senses = deck_hints.get(normalize(context.word), [])
        # Keep different meanings of the same expression attached to their own cards.
        matches = [sense for sense in senses if normalize(sense.get('meaning', '')) == normalize(context.meaning)]
        if matches or (not context.meaning and len(senses) == 1):
            entry = (matches or senses)[0]
            if entry.get('example', '').strip() or entry.get('explanation', '').strip():
                return {key: value for key, value in entry.items() if key != 'meaning'}
    entry = vocabulary.get(lookup_word(context.word))
    if entry:
        return {**entry, 'source': 'Español B1 · biblioteca local'}
    return None


def is_current(request_token: str, current_token: str, reviewing: bool) -> bool:
    return reviewing and request_token == current_token
