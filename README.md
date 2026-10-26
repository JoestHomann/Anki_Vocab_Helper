# Spanish Helper for Anki

A compact toolbar in the Anki desktop review screen. It uses Anki's own light/dark theme colors and button shapes, above the separate answer/rating bar:

- **Pronunciar** plays the current Spanish word or a selected phrase. **Alt+P** also works.
- **Pista** shows an example or explanation. **Alt+H** shows/hides the hint. When an example is available, the small speaker button beside it (**Escuchar ejemplo**) reads the whole sentence using your pronunciation and slow-audio settings. It ignores selected text and does not regenerate the hint or require an AI key. Definition-only hints have no example speaker.
- **Comprobar** checks your saved Spanish word–translation pair with AI after you reveal the answer. **Alt+C** opens/closes the result. It can use your eligible ChatGPT subscription without an API key, or a separately billed API key. The result reports a likely match, a nuance, a possible error, or uncertainty, with a suggested translation when appropriate. It checks the full saved pair, regardless of any selected text, and never edits your card.

The interface and prepared examples use Spanish appropriate for a B1 learner. Saved dictionary hints have variable difficulty and are labelled accordingly. It follows both sides of the current card, clears hints on the next card, and ignores delayed responses for old cards. Notes, templates, scheduling and review history are never edited.

## Install

1. Download/open `output/spanish-helper.ankiaddon`.
2. In Anki, select **Tools → Add-ons → Install from file…** and choose it.
3. Restart Anki and start a review. Use **Tools → Spanish Helper…** for settings.

For a first local installation, run (restart Anki afterwards if it is already open):

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\install.ps1
```

For an existing local installation, add `-Update`. The installer backs up the old add-on code and settings under `Anki2/addon_backups/` and preserves settings and cached audio. Restart Anki to load the update.

## Use your ChatGPT subscription (Windows)

1. Restart Anki after installing v1.3.0 or later.
2. Open **Tools / Extras → Spanish Helper…**.
3. Select **Suscripción de ChatGPT (sin clave API)** under **Usar IA con** (the default).
4. Click **Continue with ChatGPT**, sign in in your browser, and allow the add-on to use your plan. No API key is needed.
5. Choose a model offered by your account, or keep Automatic, and save. Automatic prefers an available Luna model; it never assumes an API-only model is included.

Eligible ChatGPT Plus/Pro accounts can use plan allowances in local personal/open-source tools through the [official Sign in with ChatGPT integration](https://developers.openai.com/siwc/token-sharing-open-source). Account eligibility and plan/app usage limits still apply. **Manage usage** opens your ChatGPT usage settings. The toolbar identifies this mode with **Using ChatGPT plan**. There is no silent fallback to paid API calls when consent, eligibility, connection, or usage limits prevent a request.

The browser callback is loopback-only, with random state, nonce, and PKCE. Identity signatures are verified using OpenAI's published signing keys and Windows CNG. OAuth sessions are encrypted with Windows DPAPI in the installed add-on's `user_files/chatgpt/` folder, separate for each Anki profile. Rotating refresh tokens are updated atomically and refreshes are serialized. No access/refresh tokens are written to configuration, logs, Git, or the preview server. Use the account picker to reconnect an existing registration or **Añadir una cuenta** to register another. **Cerrar sesión** revokes the active renewable session when possible and clears its local tokens; if revocation cannot be confirmed, the UI directs you to disconnect the app in ChatGPT settings. Existing API-key settings are preserved and used only if you explicitly select API-key mode.

End-to-end eligibility and live inference must be confirmed by completing your own sign-in. Automated tests use synthetic identities and controlled Responses streams; no real ChatGPT account was connected during development. The subscription integration uses Windows OS APIs and is currently Windows-only.

## Translation checks with an API key (optional)

If you choose **Clave API (facturación aparte)** in settings, enter your OpenAI API key once, leave **Recordar la clave en este equipo (Windows)** checked, and save. The add-on stores it in Windows Credential Manager for this Anki profile and restores it automatically when needed after restarting Anki. It is tied to your Windows account and this computer, not saved in add-on configuration, Anki sync, exported decks, backups of the add-on, or Git. Checking works independently of the AI-hint checkbox. API-key mode requires separate API billing/credit; it does not use your ChatGPT subscription.

To forget it, click **Olvidar al guardar** and then **Save**. Cancel leaves the saved key unchanged. To use a key only for the current session, uncheck **Recordar** and save; any key previously saved for this profile is removed from Credential Manager. Storage failures are reported and keep the settings dialog open. `OPENAI_API_KEY` remains an optional fallback and is never changed by the add-on; deleting the saved key does not delete an environment variable you configured yourself. On other operating systems, secure remembering is unavailable, so use a session key or the environment variable. Keys are not copied automatically from an already-running older add-on: enter yours once after installing this update.

The checker sends only the Spanish word, your saved translation (up to 500 characters), and your card's example if present (up to 500 characters). It does not use the existing deck-hint library as evidence: those hints were prepared using the very translations being checked. The request uses `store: false`. Checks run only on an explicit click/shortcut after revealing the answer. Repeated checks of the same pair/model/example use a profile-session cache; edits and model changes select a new cache entry. Closing a profile clears the cache and session key.

Set **Campo de traducción** if your saved translation uses a custom field. Otherwise `Translation`, `Meaning`, `Traducción`, `Back`, `answer`, and common German names are recognized. Set **Campo español** explicitly for unusual/reverse layouts. A missing field or key produces setup guidance, never a guessed verdict. AI results are suggestions, not authoritative verification; valid synonyms and individual meanings should be accepted, and ambiguity may produce an inconclusive result.

**Modelo para comprobar** defaults to `gpt-6-luna`, separately from the hint model. As checked on 26 October 2026, its standard API rate is $0.10 per million input tokens and $0.50 per million output tokens ([official model/pricing documentation](https://developers.openai.com/api/docs/models/gpt-6-luna)). An illustrative 500-input/200-output-token check costs $0.00015, or $0.15 for 1,000 checks; actual usage varies. There is no free OpenAI API tier for this feature.

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

For B1 explanations of words outside the local library, enable **Generar pistas B1 cuando no hay pista local**. These requests use your selected ChatGPT-plan or API-key mode. On Windows, **Recordar** securely saves an optional API key for reuse by this profile. API-key mode also supports session-only keys or `OPENAI_API_KEY`. Its hint model defaults to `gpt-4.1-mini`; subscription mode uses the account's model catalog. No AI requests happen merely by opening a card.

If a word has no local hint, dictionary example, or Spanish definition, the helper explains how to add an `Ejemplo` field or enable AI. Inflected words and regional expressions may be absent from the dictionary. Select the base form where possible. The local library matches articles (e.g. `la manzana`) but does not pretend to be a complete dictionary or automatic conjugation engine.

## Pronunciation and privacy

Online pronunciation uses Google's public Translate TTS endpoint and caches MP3s locally in the add-on's `user_files/audio` folder. Internet access is required on the first request for each word. This public endpoint has no service guarantee and can be rate-limited. An error is shown with a retry path if it is unavailable. Turn off online pronunciation to use an installed Spanish OS voice through Anki instead; Windows must actually have a Spanish voice installed.

The example speaker uses the same audio cache and voice settings. Examples longer than 180 characters are downloaded in short segments and queued in order, so the sentence is not cut off. It supports examples up to 1,500 characters. Audio responses for a previous card or replaced hint are ignored; errors allow another attempt.

Only clicking a button sends text to a service. Google receives the chosen word/phrase; the dictionary receives a search word. For AI hints, OpenAI receives the chosen word and a short translation field to help select its meaning. For translation checks, it receives the saved pair and optional example. Both use response storage disabled in the request. No full deck, collection, API key or note HTML is sent to the preview server. AI results may need correction, especially for ambiguous vocabulary.

Wiktionary examples are obtained from [Free Dictionary API](https://freedictionaryapi.com/), with definitions obtained directly from [Spanish Wiktionary](https://es.wiktionary.org/). A link to the original entry is shown in the hint. That material is licensed under [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/). The local vocabulary examples are written for this project.

## Develop and preview

No third-party Python dependencies are needed by the add-on or preview server.

```powershell
py -m unittest discover -s tests -v
py tools/audit_vocabulary.py --require-complete
py tools/build.py
py tools/preview.py
```

Open <http://127.0.0.1:8765/preview/> for a working preview with sample cards, online audio, local hints, light/dark themes, and narrow layouts. Translation checks use the preview server's `OPENAI_API_KEY` if configured; the browser never receives the key. The preview uses demonstration cards and does not connect to an Anki collection. Stop the server with Ctrl+C.

The full-deck audit reads an offline collection snapshot in `output/audit/snapshot/`. The audited word-and-meaning regression fixture is in `tools/data/audited-vocabulary.json`. The audit preparation tools can extract dictionary data, select relevant senses locally, and compile `spanish_helper/deck_hints.json`; these optional preparation dependencies are not installed into Anki. Dictionary attribution is in `spanish_helper/THIRD_PARTY_NOTICES.md`.

Implementation references: [Anki hooks](https://github.com/ankitects/anki/blob/main/qt/tools/genhooks_gui.py), [Anki audio](https://github.com/ankitects/anki/blob/main/qt/aqt/sound.py), [Anki TTS](https://docs.ankiweb.net/manual/templates/fields), and [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
