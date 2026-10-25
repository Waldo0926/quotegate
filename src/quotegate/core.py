"""Check that a model's quotes really are in the passages it was given, and widen each to a sentence that
can be read on its own.

The model is asked to reply with lines like `[2] the sentence, copied` and nothing else. `check()` reads
those lines and keeps a quote only when:

- it is in the passage it names, character for character (whitespace ignored, so line breaks don't matter);
- it is long enough to say something;
- widened to the whole sentence it sits in, that sentence still reads right alone: it doesn't start with
  "This..." or "不，" (leaning on what came before), doesn't end in ":" or "；并且" (going on in what isn't
  shown), isn't a list item under "if all of the following:", a table row, a question, or a rule whose
  years are all in the past.

Nothing here calls a model. The point is that the check is plain string work, so it can't be talked round
and gives the same answer every time.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

# "[2] sentence" per line. Some models write 【2†L9-L12】 or full-width brackets, a bullet in front, or a
# colon after the number.
_LINE = re.compile(r"^\s*(?:[-*•]\s*)?[\[【](\d{1,3})(?:†[^】\]]*)?[\]】]\s*[:：]?\s*(.+?)\s*$")
_TRAILING_CITE = re.compile(r"\s*[\[【]\d{1,3}[\]】]$")
_QUOTE_MARKS = "「」『』“”\"'《》‘’ "
_FAQ_PREFIX = re.compile(r"^(?:答|问|A|Q)\s*[:：]\s*")
_LIST_ITEM = re.compile(r"^\s*(?:[·•\-*#✓✔｜|]|\d{1,2}[.、)）｜|])\s*")
_YEAR = re.compile(r"(?<!\d)(20\d\d)(?!\d)")

# A sentence that starts like this leans on the one before it, or answers a question that isn't shown.
LEANS_BACK_ZH = (r"此|该|上述|以上|这|那些|那么|其|它|如果这|如果不|不[，,。]|否[，,]|是的?[，,]|可以[，,]|不可以|不能[，,]"
                 r"|对[，,]|没错|同样|另外|此外|但|然而|因此|所以|并且|而且|或者")
LEANS_BACK_EN = (r"(?:This|That|These|Those|It|They|Such|However|But|Therefore|So|Also|Otherwise|Then"
                 r"|If not|If so|No|Yes)\b")
# A sentence that ends like this goes on in what isn't shown.
LEANS_ON_ZH = r"[:：，,、；;]|并且|而且|或者|以及|或|和|及"
LEANS_ON_EN = r"\b(?:and|or|but|including|such as)"


@dataclass(frozen=True)
class Passage:
    """One numbered passage the model was shown. `[1]` in the reply is `passages[0]`."""
    text: str
    title: str | None = None
    """When the text starts with this title on its own line, no sentence reaches back into it."""
    soft_breaks: bool = False
    """Line breaks may fall inside a sentence (WeChat articles, text pulled from a PDF). Otherwise a line
    break ends a sentence: it is a heading, a list item or a paragraph."""
    qa: bool = False
    """The passage answers the question in its title ("答：可以，…"). A sentence opening that answer may start
    with "可以，" or "No," without leaning on anything."""


@dataclass(frozen=True)
class Quote:
    passage: int        # 1-based, as the model wrote it
    text: str           # the whole sentence, on one line, list marker and "答：" removed
    start: int          # where the sentence is in passages[passage - 1].text
    end: int


@dataclass(frozen=True)
class Dropped:
    passage: int
    quote: str          # what the model wrote, or the widened sentence when it was found
    reason: str         # "not found", "too short", "too long", "needs context", "a question", "list item",
                        # "table row", "past year", "duplicate", "over the limit", or a custom check's reason


@dataclass
class Result:
    status: str
    """"ok"; or why nothing can be sent: "unsure" (the model said it doesn't know), "uncited" (no quote
    lines), "unsupported" (no quote is in its passage), "fragment" (found, but none reads right alone)."""
    kept: list[Quote] = field(default_factory=list)
    dropped: list[Dropped] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


Check = Callable[[str, Passage], "str | None"]


@dataclass
class Rules:
    min_chars: int = 6
    """Shorter quotes (not counting whitespace) say nothing on their own and are dropped as "too short"."""
    max_chars: int = 180
    """A sentence widened past this is a paragraph with no full stop: dropped as "too long"."""
    max_quotes: int = 4
    unsure: Sequence[str] = ("不确定", "不知道", "not sure", "don't know", "do not know")
    """A short reply containing one of these means the passages don't answer the question."""
    unsure_max_chars: int = 60
    leans_back: str = f"{LEANS_BACK_ZH}|{LEANS_BACK_EN}"
    leans_on: str = f"{LEANS_ON_ZH}|{LEANS_ON_EN}"
    stops: str = "✓✔｜"
    """Characters that end a sentence even with no full stop: checklist marks, "10｜" section numbers."""
    current_year: int | None = None
    """For the past-year check: a sentence whose years are all before this one is dropped. None means this
    year; 0 turns the check off."""
    checks: Sequence[Check] = ()
    """More checks, run on each sentence that passed the rest. Return a reason to drop it, or None."""

    def __post_init__(self) -> None:
        self._back = re.compile(f"^(?:{self.leans_back})") if self.leans_back else None
        self._on = re.compile(f"(?:{self.leans_on})$") if self.leans_on else None


def parse(reply: str) -> list[tuple[int, str]]:
    """The `[n] quote` lines of a reply, quote marks and a trailing `[n]` removed. Other lines are ignored."""
    out = []
    for line in reply.splitlines():
        m = _LINE.match(line)
        if m:
            quote = _TRAILING_CITE.sub("", m.group(2).strip(_QUOTE_MARKS)).strip(_QUOTE_MARKS)
            out.append((int(m.group(1)), quote))
    return out


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _ends_at(text: str, i: int) -> bool:
    """Whether text[i] ends a sentence. A latin full stop counts only before whitespace or the end, so
    "4.0", "e.g" inside a word and URLs don't."""
    c = text[i]
    if c in "。！？!?":
        return True
    return c == "." and (i + 1 == len(text) or text[i + 1].isspace())


def _soft_break(text: str, i: int, p: Passage, rules: Rules) -> bool:
    """Whether the line break at text[i] is inside a sentence."""
    if not p.soft_breaks:
        return False
    before, after = text[:i].rstrip(), text[i + 1:].lstrip()
    if not before or not after or _LIST_ITEM.match(after):
        return False
    last = len(before) - 1
    return not _ends_at(before, last) and before[-1] not in "：:；;" + rules.stops


def sentence(quote: str, p: Passage, rules: Rules | None = None) -> tuple[int, int] | None:
    """Where the sentence holding `quote` starts and ends in the passage (whitespace ignored when finding
    it), or None when the quote isn't in it."""
    rules = rules or Rules()
    text = p.text
    idx = [i for i, c in enumerate(text) if not c.isspace()]
    q = _squash(quote)
    at = "".join(text[i] for i in idx).find(q)
    if not q or at < 0:
        return None
    start, end = idx[at], idx[at + len(q) - 1] + 1
    floor = text.find("\n") + 1 if p.title and text.startswith(p.title + "\n") else 0
    while start > floor and not _ends_at(text, start - 1) and text[start - 1] not in rules.stops \
            and not (text[start - 1] == "\n" and not _soft_break(text, start - 1, p, rules)):
        start -= 1
    while end < len(text) and not _ends_at(text, end - 1) and text[end] not in rules.stops \
            and not (text[end] == "\n" and not _soft_break(text, end, p, rules)):
        end += 1
    while start < end and text[start].isspace():
        start += 1
    return start, end


def _one_line(text: str) -> str:
    """A sentence on one line: breaks inside it go, with a space kept only between two latin words."""
    def join(m: re.Match) -> str:
        a, b = m.string[m.start() - 1:m.start()], m.string[m.end():m.end() + 1]
        return " " if a.isascii() and b.isascii() and a.isalnum() and b.isalnum() else ""
    return re.sub(r"\s*\n\s*", join, text).strip()


def _list_header(text: str, start: int) -> str | None:
    """For a sentence that is a list item, the line above the list; None when it isn't a list item."""
    line_start = text.rfind("\n", 0, start) + 1
    if not _LIST_ITEM.match(text[line_start:start + 1]):
        return None
    lines = text[:line_start].rstrip("\n").split("\n")
    while lines and _LIST_ITEM.match(lines[-1]):
        lines.pop()
    return lines[-1].strip() if lines else ""


def judge(n: int, quote: str, passages: Sequence[Passage], rules: Rules | None = None) -> Quote | Dropped:
    """One quote: the sentence to send, or why not."""
    rules = rules or Rules()
    if not 1 <= n <= len(passages):
        return Dropped(n, quote, "not found")
    if len(_squash(quote)) < rules.min_chars:
        return Dropped(n, quote, "too short")
    p = passages[n - 1]
    span = sentence(quote, p, rules)
    if span is None:
        return Dropped(n, quote, "not found")
    whole = _one_line(p.text[span[0]:span[1]])
    bare = _LIST_ITEM.sub("", _FAQ_PREFIX.sub("", whole), count=1).strip()

    def drop(reason: str) -> Dropped:
        return Dropped(n, whole, reason)

    if len(bare) > rules.max_chars:
        return drop("too long")
    opens_answer = p.qa and bool(_FAQ_PREFIX.match(whole))
    if (rules._back and rules._back.match(bare) and not opens_answer) or (rules._on and rules._on.search(bare)):
        return drop("needs context")
    if bare.endswith(("？", "?")):
        return drop("a question")
    header = _list_header(p.text, span[0])
    if header is not None and header.endswith((":", "：")):
        return drop("list item")
    # A table row without its header row ("Oct intake | OCT-MY-01 | 6 Jan") can't be read right.
    if " | " in bare or "\t" in p.text[span[0]:span[1]]:
        return drop("table row")
    # A date or rule from a past year is no answer now. One that runs into this year or later still holds.
    year = time.localtime().tm_year if rules.current_year is None else rules.current_year
    years = [int(y) for y in _YEAR.findall(bare)]
    if year and years and max(years) < year:
        return drop("past year")
    for extra in rules.checks:
        reason = extra(bare, p)
        if reason:
            return drop(reason)
    return Quote(n, bare, span[0], span[1])


def check(reply: str, passages: Sequence[Passage | str], rules: Rules | None = None) -> Result:
    """Read a model's reply and keep only the quotes that are in their passages and read right alone, in
    the order the model gave them, at most `rules.max_quotes`."""
    rules = rules or Rules()
    ps = [p if isinstance(p, Passage) else Passage(p) for p in passages]
    text = reply.strip()
    if not text or (len(text) <= rules.unsure_max_chars and any(u in text.lower() for u in rules.unsure)):
        return Result("unsure")
    kept: list[Quote] = []
    dropped: list[Dropped] = []
    lines = parse(text)
    for n, quote in lines:
        verdict = judge(n, quote, ps, rules)
        if isinstance(verdict, Dropped):
            dropped.append(verdict)
        elif any((k.passage, k.text) == (verdict.passage, verdict.text) for k in kept):
            dropped.append(Dropped(n, verdict.text, "duplicate"))
        elif len(kept) >= rules.max_quotes:
            dropped.append(Dropped(n, verdict.text, "over the limit"))
        else:
            kept.append(verdict)
    if kept:
        return Result("ok", kept, dropped)
    if not lines:
        return Result("uncited", [], dropped)
    found = [d for d in dropped if d.reason not in ("not found", "too short")]
    return Result("fragment" if found else "unsupported", [], dropped)
