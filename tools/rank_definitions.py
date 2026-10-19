"""Audit-only local multilingual ranking; no deck text is sent to a server.

Requires the optional libraries under output/audit/python. Neither the model nor
these dependencies are included in the Anki add-on or needed while studying.
"""
from pathlib import Path
import json
import os
import sys
from urllib.request import urlopen, Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'output/audit/python'))
sys.path.insert(0, str(ROOT / 'tools'))
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

from compile_deck_hints import core, load_authored, options_for


def main():
    import numpy as np
    import torch
    from transformers import AutoTokenizer, AutoModel
    torch.set_num_threads(4)
    out = ROOT / 'output/audit'
    model_dir = out / 'e5-model'
    model_dir.mkdir(exist_ok=True)
    revision = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
    for name in ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'model.safetensors'):
        path = model_dir / name
        if path.exists():
            continue
        url = f'https://huggingface.co/intfloat/multilingual-e5-small/resolve/{revision}/{name}'
        print('Downloading local matching model:', name, flush=True)
        temporary = path.with_suffix('.part')
        size = 0
        with urlopen(Request(url, headers={'User-Agent': 'SpanishAnkiHelper/1.0'}), timeout=60) as response, temporary.open('wb') as handle:
            while block := response.read(1024 * 1024):
                handle.write(block)
                size += len(block)
                if size % (100 * 1024 * 1024) == 0:
                    print('Downloaded', size // (1024*1024), 'MB', flush=True)
        temporary.replace(path)
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    model = AutoModel.from_pretrained(model_dir, local_files_only=True, use_safetensors=True).eval()
    items = json.loads((out / 'vocabulary-inventory.json').read_text(encoding='utf-8'))
    matches = json.loads((out / 'dictionary-matches.json').read_text(encoding='utf-8'))
    vocabulary = json.loads((ROOT / 'spanish_helper/vocabulary.json').read_text(encoding='utf-8'))
    authored = load_authored()
    tasks = []
    texts = []
    text_index = {}
    def index(text):
        if text not in text_index:
            text_index[text] = len(texts)
            texts.append(text)
        return text_index[text]
    for item in items:
        key = (core.normalize(item['word']), core.normalize(item['meaning']))
        context = core.CardContext(item['word'], item['example'], item['explanation'], item['meaning'])
        if core.local_hint(context, vocabulary) or key in authored:
            continue
        options = options_for(item, matches)
        if len(options) <= 1:
            continue
        query = index('query: ' + item['meaning'])
        passages = [index('passage: ' + option['definition']) for option in options]
        tasks.append((item, key, query, passages, options))
    print('Ranking', len(tasks), 'ambiguous entries using', len(texts), 'short texts locally.', flush=True)
    vectors = []
    with torch.inference_mode():
        for start in range(0, len(texts), 48):
            encoded = tokenizer(texts[start:start+48], padding=True, truncation=True, max_length=96, return_tensors='pt')
            hidden = model(**encoded).last_hidden_state
            mask = encoded['attention_mask'].unsqueeze(-1)
            pooled = (hidden * mask).sum(1) / mask.sum(1)
            vectors.append(torch.nn.functional.normalize(pooled, p=2, dim=1).numpy())
            if start % 480 == 0:
                print('Matched text batch:', start, '/', len(texts), flush=True)
    vectors = np.concatenate(vectors)
    result = {}
    review = []
    for item, key, query, passages, options in tasks:
        similarities = vectors[passages] @ vectors[query]
        scores = similarities.copy()
        for n, option in enumerate(options):
            meaning = core.normalize(item['meaning'])
            if any(core.normalize(t) in meaning for t in option['translations'] if len(t) > 3):
                scores[n] += 0.12
            scores[n] -= min(option['priority'], 2) * 0.008
            if option['noun_match']:
                scores[n] += 0.025
        order = np.argsort(scores)[::-1]
        winner = options[int(order[0])]
        result['\x1f'.join(key)] = {'definition': winner['definition'], 'score': float(similarities[order[0]])}
        review.append({'word': item['word'], 'meaning': item['meaning'],
                       'definition': winner['definition'], 'score': float(similarities[order[0]]),
                       'margin': float(scores[order[0]] - scores[order[1]])})
    (out / 'sense-ranking.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'sense-review.json').write_text(json.dumps(sorted(review, key=lambda r:r['score']), ensure_ascii=False, indent=2), encoding='utf-8')
    print('Finished local matching:', len(result), 'entries.', flush=True)


if __name__ == '__main__':
    main()
