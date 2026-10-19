"""Extract only useful Spanish entries for this user's inventory from a bulk dump.

The downloaded dump stays in output/, outside the packaged add-on. Source/licence
metadata is retained with each extracted hint; no per-word scraping is needed.
"""
from pathlib import Path
import gzip
import json
import re
import sys
import types
import importlib
from urllib.request import Request, urlopen
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType('spanish_helper')
package.__path__ = [str(ROOT / 'spanish_helper')]
sys.modules['spanish_helper'] = package
core = importlib.import_module('spanish_helper.core')
OUT = ROOT / 'output/audit'


def candidates(word):
    text = core.normalize(word)
    text = re.sub(r'\((?:g|ie|ue|i|y|zc|j|pl|m|f|fam|adj|adv|coloq)(?:\s*,\s*(?:g|ie|ue|i|y|zc|j))*\)', '', text)
    text = re.sub(r'^(?:el/la|los/las|un/una)\s+', '', text)
    # Gender alternatives and the deck's optional prepositions are not part of a lemma.
    text = re.sub(r'([\wáéíóúñ]+)/-?[\wáéíóúñ]+', r'\1', text)
    alternatives = re.split(r'\s+/\s+|\s*;\s*', text)
    result = []
    for alternative in alternatives:
        for variant in (alternative, re.sub(r'\([^)]*\)', '', alternative)):
            value = core.lookup_word(re.sub(r'\s+', ' ', variant).strip())
            if value and value not in result:
                result.append(value)
    # These are lookup candidates only: use them only when an actual dictionary entry exists.
    for value in list(result):
        if ' ' not in value and value.endswith('s'):
            for singular in (value[:-1], value[:-2] if value.endswith('es') else ''):
                if len(singular) >= 3 and singular not in result:
                    result.append(singular)
    return result


def main():
    inventory = json.loads((OUT / 'vocabulary-inventory.json').read_text(encoding='utf-8'))
    wanted = {candidate for item in inventory for candidate in candidates(item['word'])}
    dump = OUT / 'eswiktionary.jsonl.gz'
    headers = {'User-Agent': 'SpanishAnkiHelper/1.0 (personal offline dictionary audit)'}
    if not dump.exists():
        page_url = 'https://kaikki.org/eswiktionary/rawdata.html'
        with urlopen(Request(page_url, headers=headers), timeout=30) as response:
            html = response.read().decode()
        links = re.findall(r'href="([^"]+)"', html)
        link = next(link for link in links if link.endswith('.jsonl.gz') and 'error' not in link)
        url = urljoin(page_url, link)
        print('Downloading official bulk dictionary:', url, flush=True)
        temporary = dump.with_suffix('.part')
        total = 0
        with urlopen(Request(url, headers=headers), timeout=60) as response, temporary.open('wb') as handle:
            while block := response.read(1024 * 1024):
                handle.write(block)
                total += len(block)
                if total % (20 * 1024 * 1024) < 1024 * 1024:
                    print('Downloaded', round(total / 1e6), 'MB', flush=True)
        temporary.replace(dump)
    matches = {}
    count = 0
    with gzip.open(dump, 'rt', encoding='utf-8') as handle:
        for line in handle:
            count += 1
            entry = json.loads(line)
            word = core.normalize(entry.get('word', ''))
            if entry.get('lang_code') != 'es' or word not in wanted:
                continue
            useful = []
            for sense in entry.get('senses', []):
                if 'form-of' in sense.get('tags', []):
                    continue
                glosses = sense.get('glosses', [])
                if not glosses:
                    continue
                definition = core.plain_text(glosses[-1])
                if len(definition) < 8 or re.match(r'(?i)(forma (?:del|de)|(?:femenino|plural|participio|gerundio) de)', definition):
                    continue
                examples = [core.plain_text(e.get('text', '')) for e in sense.get('examples', [])]
                examples = [e for e in examples if 20 <= len(e) <= 240]
                useful.append({'definition': definition, 'examples': examples[:2], 'sense_index': sense.get('sense_index', '')})
            if useful:
                matches.setdefault(word, []).append({'senses': useful[:12], 'pos': entry.get('pos', ''),
                    'translations': [t for t in entry.get('translations', []) if t.get('lang_code') == 'de']})
            if count % 200000 == 0:
                print('Read', count, 'entries; matched', len(matches), flush=True)
    path = OUT / 'dictionary-matches.json'
    path.write_text(json.dumps(matches, ensure_ascii=False, indent=2), encoding='utf-8')
    gaps = [item for item in inventory if not any(candidate in matches for candidate in candidates(item['word']))]
    (OUT / 'dictionary-gaps.json').write_text(json.dumps(gaps, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Inventory:', len(inventory), 'Dictionary matches:', len(inventory)-len(gaps), 'Needs authored hint:', len(gaps), flush=True)


if __name__ == '__main__':
    main()
