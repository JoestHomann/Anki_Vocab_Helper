# Spanish Helper

Use **Tools → Spanish Helper…** to connect your ChatGPT account and choose settings. AI features use your eligible subscription, subject to plan/app limits. **Continue with ChatGPT** opens browser sign-in; **Manage usage** opens ChatGPT usage settings. Account selection and sign-out are available. Sessions are protected with Windows DPAPI and remembered separately for each Anki profile. Subscription sign-in currently requires Windows.

- `word_field`: exact name of the Spanish field. Empty detects the field visible on the card. Set this for decks with unusual layouts. Selection on the displayed card overrides it.
- `translation_field`: exact name of the saved translation field. Empty detects common names such as `Translation`, `Traducción`, `Back`, `answer`, or `Übersetzung`. An explicitly configured missing field stays empty; it never falls back to a different field.
- `chatgpt_model`: a model slug from the signed-in account's offered catalog, used for both hints and translation checks. Empty selects an available Luna model where offered, otherwise the first offered model. Checking works even when `ai_hints` is off. Sends the saved word, translation and optional example only when you press **Comprobar** / **Alt+C** after revealing the answer. Does not change the saved translation.
- `example_field`, `hint_field`: optional fields containing your own Spanish examples and explanations. Common names such as `Ejemplo`, `Example`, `Pista`, and `Hint` work automatically.
- `online_audio`: Google Translate pronunciation. The selected word is sent only when you click Pronunciar. With this off, an installed Spanish OS voice is required.
- `online_dictionary`: Spanish examples from Wiktionary via Free Dictionary API, falling back to a definition from Spanish Wiktionary if no example is available. These original examples and definitions are not necessarily B1.
- `ai_hints`: generate new B1 Spanish examples and explanations when no card/local hint exists. Requires browser sign-in and permission to use your ChatGPT plan. No AI requests happen just by opening a card.
- `slow_audio`: slower pronunciation for both the card word and the hint example speaker.

When a hint contains an example, **Escuchar ejemplo** (the small speaker beside the sentence) reads that complete example, not a text selection or the card word. It uses `online_audio` and `slow_audio`; no AI key is needed. Long examples are played as ordered cached audio segments, up to 1,500 characters. With `online_audio` off, an installed Spanish OS voice reads the sentence instead.

No notes, card templates, scheduling, or review history are changed. Cached MP3s are stored in `user_files/audio`. Closing a profile clears in-memory results. OAuth secrets are never stored in configuration or synced with Anki.

**Ask AI** / **Alt+A** opens a card chat with suggested questions about meaning, translation, grammar, tenses/conjugation, and examples. You can type custom questions and follow-ups; Enter sends and Shift+Enter inserts a new line. Chat uses the same `chatgpt_model` and subscription. Opening it makes no AI request. Before revealing the answer, only the word is shared; after revealing it, the saved translation and example are included. Questions are limited to 1,500 characters. The six most recent exchanges provide context for follow-ups. Chat is kept only in memory and clears when the card/side changes or the profile closes.

The API-key route has been removed. Legacy provider, API-model, and remember-key options are ignored and dropped when you save settings. This version never reads stored API keys or environment keys.

The bundled `deck_hints.json` has offline hints for all 2,480 vocabulary cards audited across the 12 Spanish vocabulary units on 19 October 2026. Prepared examples are B1; saved dictionary wording is labelled as variable difficulty. These existing-card hints do not require the online dictionary or an AI key. New cards may still need a lookup. Known `question`/`answer` field names are recognized automatically, and distinct meanings of the same headword are kept separate.
