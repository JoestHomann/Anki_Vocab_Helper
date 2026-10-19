# Spanish Helper for Anki

Local checkout: `C:\Users\joest\Anki_Vocab_Helper`.

A small overlay in the Anki desktop review screen with two buttons:

- **Pronunciar** plays the current Spanish word or a selected phrase. **Alt+P** also works.
- **Dame una pista** shows an example or explanation. **Alt+H** shows/hides the hint.

The interface and prepared examples use Spanish appropriate for a B1 learner. Saved dictionary hints have variable difficulty and are labelled accordingly. It follows both sides of the current card, clears hints on the next card, and ignores delayed responses for old cards. Notes, templates, scheduling and review history are never edited.

## Install

1. Download/open `output/spanish-helper.ankiaddon`.
2. In Anki, select **Tools → Add-ons → Install from file…** and choose it.
3. Restart Anki and start a review. Use **Tools → Spanish Helper…** for settings.

For a first local installation, run (restart Anki afterwards if it is already open):

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\install.ps1
```

Desktop Anki with Python 3.9+ and Qt 6 is the target. It does not run in AnkiWeb, AnkiDroid or AnkiMobile. The integration is checked against the installed Anki runtime; see `output/validation.md` for actual verification results.

## Choose the Spanish text

The helper detects common field names (`Spanish`, `Español`, `Palabra`, `Expression`, `Word`, `Front`, `question`, `Vorderseite`) when that field appears on the current card side. Plain short cards also work automatically. It cannot reliably infer the Spanish vocabulary inside every custom or multilingual template.

For consistent results, set **Campo español** to the exact field name used by your deck. This explicit mapping also makes the Spanish answer available on reverse cards. Alternatively, select the Spanish word directly on the card, then click either button. Fields called `Ejemplo`/`Example` and `Pista`/`Hint` are detected automatically; custom names can be set in the settings dialog.

## Hints

The helper tries these in order:

1. Your card's own example or hint fields, if present. Their language/level depends on your content.
2. The audited offline library for all **2,480 existing vocabulary cards** in the 12 `Spanisch::Vocabulario` units. It contains 2,459 word-and-meaning entries: 969 prepared B1 examples, 25 hints from the original B1 library, and 1,465 saved Spanish dictionary hints. Different meanings of the same headword have separate records, matched using the card's translation field (`answer`, `Back`, or another recognized name).
3. The original general library of 55 B1 vocabulary hints, also available for other cards.
4. For words outside the saved libraries, OpenAI can generate a new B1 Spanish example and explanation when enabled. Otherwise, the free dictionary supplies an original Spanish usage example or a definition from Spanish Wiktionary. Original dictionary language has variable difficulty and is labelled accordingly.

The current-deck hints work without an API key or Internet connection. See `output/audit/coverage.md` for the report. New cards added after the 19 October 2026 snapshot are outside this completed coverage audit and use the regular lookup fallback.

For B1 explanations of words outside the local library, enable **Generar pistas B1 con OpenAI**, then enter an API key in the settings dialog. It stays in memory only for the current Anki profile session. Alternatively, set `OPENAI_API_KEY` locally before launching Anki. API billing is separate from a ChatGPT subscription. The model is configurable; default `gpt-4.1-mini`. No paid requests happen merely by opening a card.

If a word has no local hint, dictionary example, or Spanish definition, the helper explains how to add an `Ejemplo` field or enable AI. Inflected words and regional expressions may be absent from the dictionary. Select the base form where possible. The local library matches articles (e.g. `la manzana`) but does not pretend to be a complete dictionary or automatic conjugation engine.

## Pronunciation and privacy

Online pronunciation uses Google's public Translate TTS endpoint and caches MP3s locally in the add-on's `user_files/audio` folder. Internet access is required on the first request for each word. This public endpoint has no service guarantee and can be rate-limited. An error is shown with a retry path if it is unavailable. Turn off online pronunciation to use an installed Spanish OS voice through Anki instead; Windows must actually have a Spanish voice installed.

Only clicking a button sends text to a service. Google receives the chosen word/phrase; the dictionary receives a search word. When AI is enabled, OpenAI receives the chosen word and a short translation field to help select its meaning, with response storage disabled in the request. No full deck, collection, API key or note HTML is sent to the preview server. Generated hints may need correction, especially for ambiguous vocabulary.

Wiktionary examples are obtained from [Free Dictionary API](https://freedictionaryapi.com/), with definitions obtained directly from [Spanish Wiktionary](https://es.wiktionary.org/). A link to the original entry is shown in the hint. That material is licensed under [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/). The local vocabulary examples are written for this project.

## Develop and preview

No third-party Python dependencies are needed by the add-on or preview server.

```powershell
py -m unittest discover -s tests -v
py tools/audit_vocabulary.py --require-complete
py tools/build.py
py tools/preview.py
```

Open <http://127.0.0.1:8765/preview/> for a working preview with sample cards, online audio, local hints, light/dark themes, and narrow layouts. The preview uses demonstration cards and does not connect to an Anki collection. Stop the server with Ctrl+C.

The full-deck audit reads an offline collection snapshot in `output/audit/snapshot/`. The audited word-and-meaning regression fixture is in `tools/data/audited-vocabulary.json`. The audit preparation tools can extract dictionary data, select relevant senses locally, and compile `spanish_helper/deck_hints.json`; these optional preparation dependencies are not installed into Anki. Dictionary attribution is in `spanish_helper/THIRD_PARTY_NOTICES.md`.

Implementation references: [Anki hooks](https://github.com/ankitects/anki/blob/main/qt/tools/genhooks_gui.py), [Anki audio](https://github.com/ankitects/anki/blob/main/qt/aqt/sound.py), [Anki TTS](https://docs.ankiweb.net/manual/templates/fields), and [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
