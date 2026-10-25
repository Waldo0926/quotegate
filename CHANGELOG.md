# Changelog

## 0.1.0 - 2026-10-26

First release, pulled out of the 马莫百科 WeChat bot's `wxbot/rag.py`.

- `check(reply, passages, rules)` reads `[n] sentence` lines and keeps a quote only when it is in passage n (whitespace ignored), widened to the whole sentence, and that sentence reads right alone. Dropped quotes come back with a reason.
- Chinese and English: sentence ends, connectives that lean on text not shown, list items under a colon, FAQ "答：" / "Q:" prefixes.
- `Rules` for lengths, connectives, stop characters, the past-year check and custom checks.
- `quotegate.prompts`: English and Chinese system prompts asking for that format.
