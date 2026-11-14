# Languages — every country, every language

LocalBotz ships a catalogue of **199 countries and 186 languages** (`languages.json`):
every country with its official language(s), and every language with its
ISO code, English name and native name.

## Where it comes from

- Country names and codes: ISO 3166 (via `pycountry`).
- Language names and codes: ISO 639-1 (via `pycountry`), plus Filipino
  (`fil`) and Cantonese (`yue`), which have no ISO 639-1 code — they are
  marked as such in the file.
- Which language is official where: Unicode CLDR territory-language data
  (via `Babel`), national + de facto + regional official languages.
- Compiled November 2026. To regenerate: install `pycountry` and `Babel`
  and run the generator (see `languages.json`'s top note for the sources).

## How to use it

- **Languages page** (🌍 in the sidebar): search any country or language,
  see its official language(s), and press **Use** to make the bot you have
  open reply in that language.
- **Make a bot**: the Language menu — Auto (default) replies in the
  language the user wrote in; pick a language and the bot always replies
  in it.
- **Chat header**: the language menu at the top of the chat changes the
  reply language for this chat only — the bot itself is unchanged.
  “All languages…” opens the Languages page.
- **Settings → General → Default language**: the default for every bot
  that has no language of its own. A bot's language overrides it.

Precedence: per-chat choice → bot's language → global default → Auto.

## Talk follows the language

When you tap 🎙️ Talk, the microphone listens in the bot's language
(and Auto uses your browser's language). Spoken replies use a matching
voice when the browser has one, and fall back to the default voice
otherwise. Nothing is recorded — Talk still sends no audio anywhere
except to the browser's own speech service.

## Honest limits — read this before promising anything

- **The AI understands a language as well as the model behind it does.**
  Local Qwen3.5 is strong in English, Chinese, Arabic and many others,
  but it is not equally fluent in all 186 languages, and neither is any
  online provider. A language being listed means LocalBotz knows its name
  and code — not that every model speaks it well.
- **Speech depends on the browser and the operating system**, not on
  LocalBotz. Chrome and Edge ship speech recognition and voices for many
  languages, but not for all of them, and the list changes per device.
  If a language has no voice on your computer, replies are still written
  — they just are not read out loud.
- **Right-to-left languages** (Arabic, Hebrew, Urdu, Persian, …) display
  right-to-left in chat.
- **“Auto” follows the user's message.** If you write in Arabic, the bot
  answers in Arabic; switch to English mid-chat and it switches with you
  (as well as the model can tell the languages apart).

## API

- `GET /api/languages` — the whole catalogue (countries, languages,
  common list). `?q=` searches names and codes.
- `GET /api/languages/{code}` — one language, plus the countries where
  it is official. 404 for an unknown code.
- `GET /api/countries` — all countries with their official language(s).
  `?q=` searches names.
- `POST /api/bots` / `PATCH /api/bots/{id}` — field `language`
  (`"auto"` or a code from the catalogue; 400 on an unknown code).
- `POST /api/bots/{id}/chat` — field `language` overrides the reply
  language for that one chat only.
- `POST /api/settings` — field `default_language`.
