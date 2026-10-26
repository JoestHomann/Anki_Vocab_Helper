# Spanish Helper

Use **Tools → Spanish Helper…** for the settings dialog.

- `word_field`: exact name of the Spanish field. Empty detects the field visible on the card. Set this for decks with unusual layouts. Selection on the displayed card overrides it.
- `translation_field`: exact name of the saved translation field. Empty detects common names such as `Translation`, `Traducción`, `Back`, `answer`, or `Übersetzung`. An explicitly configured missing field stays empty; it never falls back to a different field.
- `check_model`: AI translation-check model; default `gpt-6-luna`. Requires an OpenAI API key and paid API access, separately from a ChatGPT subscription. Works even when `ai_hints` is off. Sends the saved word, translation and optional example only when you press **Comprobar** / **Alt+C** after revealing the answer. Does not use selected text or change the saved translation. Results are cached in memory for the profile session.
- `example_field`, `hint_field`: optional fields containing your own Spanish examples and explanations. Common names such as `Ejemplo`, `Example`, `Pista`, and `Hint` work automatically.
- `online_audio`: Google Translate pronunciation. The selected word is sent only when you click Pronunciar. With this off, an installed Spanish OS voice is required.
- `online_dictionary`: Spanish examples from Wiktionary via Free Dictionary API, falling back to a definition from Spanish Wiktionary if no example is available. These original examples and definitions are not necessarily B1.
- `ai_hints`: generate new B1 Spanish examples and explanations when no card/local hint exists. Requires an OpenAI API key entered in settings, restored from Windows Credential Manager, or supplied by `OPENAI_API_KEY`. API usage is billed separately.
- `remember_api_key`: remember a key entered in settings using Windows Credential Manager, separately for each Anki profile on this computer (default true on Windows). The key itself is never stored in this configuration. Uncheck and save to remove the stored key while using the entered key for the current session. **Olvidar al guardar** clears the field and removes the stored key when you save; Cancel leaves storage unchanged. The add-on never changes Windows environment variables. Secure remembering is unavailable on other operating systems.
- `model`: configurable OpenAI Responses API model; default `gpt-4.1-mini`.
- `slow_audio`: slower pronunciation for both the card word and the hint example speaker.

When a hint contains an example, **Escuchar ejemplo** (the small speaker beside the sentence) reads that complete example, not a text selection or the card word. It uses `online_audio` and `slow_audio`; no AI key is needed. Long examples are played as ordered cached audio segments, up to 1,500 characters. With `online_audio` off, an installed Spanish OS voice reads the sentence instead.

No notes, card templates, scheduling, or review history are changed. Cached MP3s are stored in `user_files/audio`. The in-memory key is cleared when a profile closes. If remembering is enabled, the profile's key is restored from Windows Credential Manager when it is next needed. Storage failures are reported instead of falling back to plaintext files.

The bundled `deck_hints.json` has offline hints for all 2,480 vocabulary cards audited across the 12 Spanish vocabulary units on 19 October 2026. Prepared examples are B1; saved dictionary wording is labelled as variable difficulty. These existing-card hints do not require the online dictionary or an AI key. New cards may still need a lookup. Known `question`/`answer` field names are recognized automatically, and distinct meanings of the same headword are kept separate.
