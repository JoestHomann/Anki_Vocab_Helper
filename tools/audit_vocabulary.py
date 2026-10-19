"""Audit every Spanish vocabulary note in an offline Anki snapshot."""
from pathlib import Path
import argparse
import collections
import importlib
import json
import sqlite3
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType('spanish_helper')
package.__path__ = [str(ROOT / 'spanish_helper')]
sys.modules['spanish_helper'] = package
core = importlib.import_module('spanish_helper.core')


def inventory(snapshot):
    connection = sqlite3.connect(snapshot.resolve().as_uri() + '?mode=ro', uri=True)
    connection.create_collation('unicase', lambda a, b: (a.casefold() > b.casefold()) - (a.casefold() < b.casefold()))
    columns = collections.defaultdict(list)
    for note_type, ordinal, name in connection.execute('SELECT ntid,ord,name FROM fields ORDER BY ntid,ord'):
        columns[note_type].append(name)
    rows = connection.execute('''SELECT DISTINCT n.id,n.mid,n.flds,d.name FROM notes n
        JOIN cards c ON c.nid=n.id JOIN decks d ON d.id=CASE WHEN c.odid!=0 THEN c.odid ELSE c.did END
        WHERE d.name LIKE ?''', ('Spanisch' + chr(31) + 'Vocabulario%',)).fetchall()
    connection.close()
    items = {}
    for note_id, note_type, field_values, deck in rows:
        fields = dict(zip(columns[note_type], field_values.split(chr(31))))
        visible = core.first_field(fields, ['Spanish', 'Español', 'Palabra', 'question', 'Front', 'Vorderseite'])
        context = core.extract_context(fields, visible, {})
        key = (core.normalize(context.word), core.normalize(context.meaning))
        entry = items.setdefault(key, {'word': context.word, 'meaning': context.meaning,
            'example': context.example, 'explanation': context.explanation, 'note_ids': [], 'decks': []})
        if note_id not in entry['note_ids']:
            entry['note_ids'].append(note_id)
        if deck not in entry['decks']:
            entry['decks'].append(deck)
    return list(items.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'output/audit/snapshot/collection.anki2')
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    items = inventory(args.snapshot)
    out = ROOT / 'output/audit'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'vocabulary-inventory.json').write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    vocabulary = json.loads((ROOT / 'spanish_helper/vocabulary.json').read_text(encoding='utf-8'))
    path = ROOT / 'spanish_helper/deck_hints.json'
    deck_hints = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    covered = []
    gaps = []
    for item in items:
        context = core.CardContext(item['word'], item['example'], item['explanation'], item['meaning'])
        hint = core.local_hint(context, vocabulary, deck_hints)
        (covered if hint and (hint.get('example', '').strip() or hint.get('explanation', '').strip()) else gaps).append(item)
    report = {'notes': sum(len(item['note_ids']) for item in items), 'distinct_entries': len(items),
              'covered_entries': len(covered), 'missing_entries': len(gaps),
              'covered_notes': sum(len(item['note_ids']) for item in covered),
              'missing': gaps, 'by_source': dict(collections.Counter(
                  core.local_hint(core.CardContext(item['word'], item['example'], item['explanation'], item['meaning']), vocabulary, deck_hints)['source'] for item in covered))}
    (out / 'coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Spanish vocabulary hint coverage', '',
        f'- Vocabulary cards checked: **{report["notes"]}**',
        f'- Distinct word-and-meaning entries: **{len(items)}**',
        f'- Entries with a usable offline hint: **{len(covered)}**',
        f'- Missing hints: **{len(gaps)}**', '',
        'Scope: the 12 units in `Spanisch::Vocabulario`, including suspended cards and cards in filtered decks. Grammar cards are outside this vocabulary audit.', '',
        '## Available hint sources', '', '| Source | Entries |', '|---|---:|']
    for source, count in report['by_source'].items():
        lines.append(f'| {source} | {count} |')
    lines += ['', 'Prepared examples use B1 Spanish. Original dictionary definitions and examples have variable difficulty and retain source links. Dictionary senses were matched against the meaning recorded on each card; this is coverage verification, not a manual linguistic review of every dictionary definition.', '',
        'The original collection was not edited. The audit used a consistency-checked snapshot; all covered hints resolve through the same local lookup used by the Anki add-on. New cards added after this snapshot may still need dictionary or AI lookup.', '',
        'Detailed data: `coverage.json` and `vocabulary-inventory.json` in the same directory.']
    (out / 'coverage.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'missing'}, ensure_ascii=False, indent=2))
    if args.require_complete and gaps:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
