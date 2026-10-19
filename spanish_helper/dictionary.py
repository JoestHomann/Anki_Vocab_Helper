"""Read numbered Spanish definitions without showing other language sections."""
from html.parser import HTMLParser
import re

from .core import plain_text


class SpanishDefinitions(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.spanish = False
        self.heading = None
        self.heading_is_spanish = False
        self.term = None
        self.numbered = False
        self.definition = None
        self.skip = []
        self.definitions = []

    def finish_definition(self):
        if self.definition is not None:
            text = plain_text(''.join(self.definition))
            if len(text) >= 8:
                self.definitions.append(text)
        self.definition = None
        self.skip = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h2':
            self.finish_definition()
            self.heading = []
            self.heading_is_spanish = attrs.get('id', '') in ('Español', 'Espa.C3.B1ol')
            self.spanish = False
            self.numbered = False
        if self.heading is not None and attrs.get('id') in ('Español', 'Espa.C3.B1ol', 'es'):
            self.heading_is_spanish = True
        if self.definition is not None:
            if tag in ('ul', 'ol', 'dl', 'sup', 'script', 'style'):
                self.skip.append(tag)
            elif tag == 'br' and not self.skip:
                self.definition.append(' ')
        elif tag == 'dt' and self.spanish:
            self.term = []
        elif tag == 'dd' and self.spanish and self.numbered:
            self.definition = []
            self.numbered = False

    def handle_endtag(self, tag):
        if tag == 'h2' and self.heading is not None:
            title = plain_text(''.join(self.heading)).casefold()
            self.spanish = self.heading_is_spanish or title == 'español'
            self.heading = None
        if tag == 'dt' and self.term is not None:
            self.numbered = bool(re.fullmatch(r'\d+[.:]?', ''.join(self.term).strip()))
            self.term = None
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.pop()
        elif tag == 'dd':
            self.finish_definition()

    def handle_data(self, data):
        if self.heading is not None:
            self.heading.append(data)
        if self.term is not None:
            self.term.append(data)
        if self.definition is not None and not self.skip:
            self.definition.append(data)


def spanish_definitions(html: str) -> list[str]:
    parser = SpanishDefinitions()
    parser.feed(html)
    parser.close()
    parser.finish_definition()
    return parser.definitions
