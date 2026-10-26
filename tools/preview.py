"""Local preview with real pronunciation and hints. Does not read any Anki collection."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import importlib
import json
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
# Load the pure service modules without executing the Anki add-on entry point.
package = types.ModuleType('spanish_helper')
package.__path__ = [str(ROOT / 'spanish_helper')]
sys.modules['spanish_helper'] = package
core = importlib.import_module('spanish_helper.core')
services = importlib.import_module('spanish_helper.services')
vocabulary = json.loads((ROOT / 'spanish_helper/vocabulary.json').read_text(encoding='utf-8'))
deck_path = ROOT / 'spanish_helper/deck_hints.json'
deck_hints = json.loads(deck_path.read_text(encoding='utf-8')) if deck_path.exists() else {}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urlsplit(self.path).path
        allowed = path in ('/preview/', '/preview/index.html', '/README.md') or (
            '..' not in path and '%' not in path and (
                path in ('/spanish_helper/web/overlay.js', '/spanish_helper/web/overlay.css') or
                (path.startswith('/output/preview-audio/') and path.endswith('.mp3'))))
        if not allowed:
            self.send_error(404)
            return
        super().do_GET()

    def do_POST(self):
        # Preview is loopback-only and only accepts JSON requests from its own page.
        if self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host', '')):
            self.send_error(403)
            return
        if self.path != '/api/helper':
            self.send_error(404)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size < 4096:
                raise ValueError('Invalid request length')
            request = json.loads(self.rfile.read(size))
            word = str(request.get('word', ''))[:180]
            if request['action'] == 'pronounce':
                path = services.get_audio(word, ROOT / 'output/preview-audio')
                result = {'event': 'audio', 'url': '/' + path.relative_to(ROOT).as_posix(), 'word': word}
            elif request['action'] == 'example_audio':
                paths = services.get_example_audio(str(request.get('example', '')), ROOT / 'output/preview-audio')
                result = {'event': 'audio', 'action': 'example_audio',
                          'urls': ['/' + path.relative_to(ROOT).as_posix() for path in paths]}
            elif request['action'] == 'hint':
                context = core.CardContext(word)
                result = {'event': 'hint', 'word': word, **(core.local_hint(context, vocabulary, deck_hints) or services.dictionary_hint(word))}
            elif request['action'] in ('check', 'chat'):
                raise services.HelperError('For AI checks and card chat, connect your ChatGPT subscription in Anki → Tools → Spanish Helper.')
            else:
                raise ValueError('Unknown action')
        except Exception as error:
            result = {'event': 'error', 'action': locals().get('request', {}).get('action', 'hint'), 'message': str(error)}
        payload = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Preview: http://127.0.0.1:{args.port}/preview/ (Ctrl+C to stop)', flush=True)
    server.serve_forever()
