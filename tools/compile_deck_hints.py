"""Compile sense-matched, offline hints for every audited Spanish vocabulary card."""
from pathlib import Path
import collections
import importlib
import json
import re
import sys
import types
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType('spanish_helper')
package.__path__ = [str(ROOT / 'spanish_helper')]
sys.modules['spanish_helper'] = package
core = importlib.import_module('spanish_helper.core')
sys.path.insert(0, str(ROOT / 'tools'))
from prepare_dictionary import candidates


def load_authored():
    inventory = json.loads((ROOT / 'tools/data/authored-inventory.json').read_text(encoding='utf-8'))
    result = {}
    for line in (ROOT / 'tools/data/authored_hints.tsv').read_text(encoding='utf-8').splitlines():
        index, example = line.split('\t', 1)
        item = inventory[int(index)]
        key = (core.normalize(item['word']), core.normalize(item['meaning']))
        assert len(example.split()) >= 4, item['word']
        result[key] = {'example': example, 'explanation': '', 'source': 'Español B1 · ejemplo preparado para tu vocabulario'}
    assert len(result) == len(inventory), 'Every dictionary gap needs its own authored example.'
    extras = json.loads((ROOT / 'tools/data/authored_extras.json').read_text(encoding='utf-8'))
    for word, senses in extras.items():
        for sense in senses:
            result[(core.normalize(word), core.normalize(sense['meaning']))] = {
                'example': sense['example'], 'explanation': '',
                'source': 'Español B1 · ejemplo preparado para tu vocabulario'}
    reviewed = json.loads((ROOT / 'tools/data/reviewed-inventory.json').read_text(encoding='utf-8'))
    seen = set()
    for line in (ROOT / 'tools/data/reviewed_hints.tsv').read_text(encoding='utf-8').splitlines():
        index, example = line.split('\t', 1)
        seen.add(int(index))
        item = reviewed[int(index)]
        result[(core.normalize(item['word']), core.normalize(item['meaning']))] = {
            'example': example, 'explanation': '',
            'source': 'Español B1 · ejemplo preparado para tu vocabulario'}
    assert len(seen) == len(reviewed)
    return result


def options_for(item, matches):
    result = []
    seen = set()
    noun = bool(re.match(r'^(el|la|los|las|el/la)\s', core.normalize(item['word'])))
    for priority, candidate in enumerate(candidates(item['word'])):
        for entry in matches.get(candidate, []):
            if entry['pos'] == 'name' and not item['word'][:1].isupper():
                continue
            for sense in entry['senses']:
                definition = sense['definition']
                if definition in seen:
                    continue
                seen.add(definition)
                translations = [t['word'] for t in entry['translations']
                    if str(t.get('sense_index', '')) == str(sense.get('sense_index', ''))]
                result.append({**sense, 'candidate': candidate, 'pos': entry['pos'],
                    'translations': translations, 'priority': priority,
                    'noun_match': noun and entry['pos'] == 'noun'})
    return result


def main():
    items = json.loads((ROOT / 'output/audit/vocabulary-inventory.json').read_text(encoding='utf-8'))
    matches = json.loads((ROOT / 'output/audit/dictionary-matches.json').read_text(encoding='utf-8'))
    vocabulary = json.loads((ROOT / 'spanish_helper/vocabulary.json').read_text(encoding='utf-8'))
    authored = load_authored()
    ranking_file = ROOT / 'output/audit/sense-ranking.json'
    rankings = json.loads(ranking_file.read_text(encoding='utf-8')) if ranking_file.exists() else {}
    hints = collections.defaultdict(list)
    chosen = []
    for item in items:
        key = (core.normalize(item['word']), core.normalize(item['meaning']))
        context = core.CardContext(item['word'], item['example'], item['explanation'], item['meaning'])
        hint = core.local_hint(context, vocabulary) or authored.get(key)
        if not hint:
            options = options_for(item, matches)
            assert options, f'No real hint for {item["word"]!r}'
            ranked = rankings.get('\x1f'.join(key))
            if ranked:
                selected = next(o for o in options if o['definition'] == ranked['definition'])
            else:
                def score(option):
                    text = core.normalize(item['meaning'])
                    exact = any(core.normalize(t) in text for t in option['translations'] if len(t) > 3)
                    return (exact, option['noun_match'], -option['priority'])
                selected = max(options, key=score)
            hint = {'example': selected['examples'][0] if selected['examples'] else '',
                    'explanation': selected['definition'],
                    'source': 'Wikcionario · guardado sin conexión (nivel variable)',
                    'url': 'https://es.wiktionary.org/wiki/' + quote(selected['candidate'], safe='')}
            chosen.append({'word': item['word'], 'meaning': item['meaning'], **selected,
                           'score': ranked.get('score') if ranked else None})
        assert hint.get('example') or hint.get('explanation'), item['word']
        hints[key[0]].append({'meaning': item['meaning'], **hint})
    path = ROOT / 'spanish_helper/deck_hints.json'
    path.write_text(json.dumps(dict(hints), ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'output/audit/selected-definitions.json').write_text(json.dumps(chosen, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Compiled', sum(map(len, hints.values())), 'sense-specific hints for', len(hints), 'headwords.')


if __name__ == '__main__':
    main()
