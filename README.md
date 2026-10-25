# quotegate

[![Tests](https://github.com/Waldo0926/quotegate/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/Waldo0926/quotegate/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)

[中文](README.zh-CN.md) · English

Let a language model answer only with sentences copied from your passages, and check every one in code before it reaches a user.

The model is told to reply with lines like `[2] a sentence, copied`. `quotegate.check()` keeps a line only when the sentence is really in passage 2 and still reads right on its own. Everything else is dropped with a reason. No second model, no network, no dependencies: plain string work that gives the same answer every time.

It was pulled out of the [马莫百科 WeChat bot](https://github.com/Waldo0926/mumguide-wechat-bot), which answers visa, enrolment and exam questions for Monash University students and parents, where a confident extra step is worse than no answer.

## Why not let the model write and cite?

| Approach | What it gives you | What it doesn't stop |
| --- | --- | --- |
| The model writes, sources attached | A fluent reply with links | Sentences no source says. An audit of four generative search engines ([Liu, Zhang and Liang, Findings of EMNLP 2023](https://aclanthology.org/2023.findings-emnlp.467/)) found only 51.5% of generated sentences fully supported by their citations |
| A second model checks the reply, e.g. [Ragas faithfulness](https://docs.ragas.io/en/v0.2.0/concepts/metrics/available_metrics/faithfulness/) | A score: the share of claims the judge finds supported | It is a judge, so it can be wrong both ways, and it scores after the fact instead of gating what is sent |
| Provider citations, e.g. [Claude's citations](https://docs.anthropic.com/en/docs/build-with-claude/citations) | Cited text guaranteed to point into your documents | Text between citations is still the model's own words, and it ties you to one paid API |
| **quotegate** | Only sentences that are in the passages, whole, each with its passage number | A true sentence that answers a different question. That is what the prompt and your retrieval are for |

In the bot this came from, a free model asked to answer in its own words added steps no passage has ("the lecturer will apply for special consideration for you") and turned "ISP takes your passport when the sticker has 14 days or less left" into "there is a 14-day grace period after it expires". A second model checking the sentences missed some of these and cut correct ones. Quoting plus a string check had neither problem.

## What gets dropped

A quote is widened to the whole sentence it sits in, then dropped when:

| Reason | Example |
| --- | --- |
| `not found` | A paraphrase, a quote on the wrong passage, a passage number that doesn't exist |
| `too short` | `[1] upload`: under 6 characters says nothing |
| `needs context` | Starts with "This must...", "However", "不，", "此流程"; ends with ":", "and", "；并且" |
| `list item` | "- you must contact ISP" under "If you don't meet any of the requirements above:" |
| `a question` | The passage's own FAQ question |
| `table row` | "Oct intake \| OCT-MY-01 \| 6 Jan": the header row isn't there |
| `past year` | "From 2022 exams are online" in 2026. "Until 31 December 2026" is kept |
| `too long` | Widened past 180 characters: a paragraph with no full stop |
| `duplicate`, `over the limit` | The same sentence twice, or more than 4 |

Line breaks end a sentence unless the passage says otherwise (`soft_breaks=True` for WeChat articles and PDF text, where lines break mid-sentence). A latin full stop ends one only before whitespace, so "50.0" and "monash.edu" don't.

## Use

```sh
pip install quotegate
```

```python
from quotegate import Passage, check
from quotegate.prompts import EN, user_message

passages = [
    Passage("Special consideration\nApply online within two working days of the due date. "
            "This must include supporting documents.", title="Special consideration"),
    Passage("Exams\nFinal exams run in weeks 13 and 14."),
]
messages = [
    {"role": "system", "content": EN},
    {"role": "user", "content": user_message("How long do I have to apply?", [p.text for p in passages])},
]
reply = call_your_model(messages)   # any chat model, e.g. a free tier
# reply == "[1] Apply online within two working days\n[1] This must include supporting documents"

result = check(reply, passages)
result.status    # "ok"
result.kept      # [Quote(passage=1, text="Apply online within two working days of the due date.", start=22, end=75)]
result.dropped   # [Dropped(passage=1, quote="This must include supporting documents.", reason="needs context")]
```

When `result.status` isn't `"ok"`, send nothing from the model: `"unsure"` (it said it doesn't know), `"uncited"` (no quote lines), `"unsupported"` (no quote is in its passage) or `"fragment"` (found, but none reads right alone). The bot this came from forwards those questions to a person.

`start` and `end` locate the sentence in the passage, so you can link or highlight it. Send `kept` with the pages they came from and a line saying they are excerpts.

### Rules

`check(reply, passages, Rules(...))`:

| Field | Default | |
| --- | --- | --- |
| `min_chars`, `max_chars`, `max_quotes` | 6, 180, 4 | |
| `leans_back`, `leans_on` | Chinese and English connectives | Regexes for a start or end that leans on text not shown. `quotegate.core` has the Chinese and English parts separately |
| `stops` | `✓✔｜` | Characters that end a sentence with no full stop |
| `current_year` | this year | For `past year`; `0` turns it off |
| `unsure` | 不确定, 不知道, not sure, ... | A short reply containing one of these is `"unsure"` |
| `checks` | none | Your own checks: `fn(sentence, passage) -> reason or None` |

`Passage(text, title=None, soft_breaks=False, qa=False)`: a text starting with its `title` line never has a sentence widened into the title; `qa=True` marks a passage that answers the question in its title, so "Yes, ..." or "可以，..." right after "答：" is fine.

## Numbers

From the bot's evaluation ([docs/EVAL.md](https://github.com/Waldo0926/mumguide-wechat-bot/blob/main/docs/EVAL.md), 50 questions, 2026-10-25, Groq's free `qwen/qwen3.8-27b`):

| | Rules only | Rules + quote-only model |
| --- | --- | --- |
| Questions with no answer in any source left to a person | 1 of 7 | 6 of 7 |
| Model calls where the check removed at least one quote | - | 8 of 29 |
| Model calls where nothing could be sent | - | 2 of 29 |

The check itself takes about 0.3 ms for a reply of four quotes against five 500-character passages (measured 2026-10-26 on one core of a cloud container).

## Not for

- Answers that need reasoning or arithmetic across passages. A quote can only say what a passage says.
- Deciding whether a sentence answers the question. Bad retrieval gives true, irrelevant quotes.
- Translation: quote in the passages' language and translate the passages ahead of time.

## Development

```sh
uv venv && uv pip install -e . pytest ruff
.venv/bin/pytest -q && .venv/bin/ruff check .
```

Releases: bump `__version__` in `src/quotegate/__init__.py`, add a `CHANGELOG.md` section, merge, then push a `v<version>` tag. `release.yml` checks the tag against the version, runs the tests and publishes to PyPI with Trusted Publishing.

## License

[MIT](LICENSE) © Waldo
