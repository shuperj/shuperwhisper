"""Deterministic cleanup for dictated text.

No AI and no network. Every rule is a regex with a test, and the goal is text
that reads like a person typed it: single spaces, no em-dashes, no filler.

clean() tidies a transcription on its own; join() fits it onto whatever text
already precedes the caret.
"""

import re
from typing import Iterable

_PUNCT = ",.;:!?"
_PUNCT_CLASS = re.escape(_PUNCT)
_SENTENCE_END = ".!?"
_OPENERS = "([{\"'“‘"

# Spoken commands, longest phrase first.
_BREAK_COMMANDS = (("new paragraph", "\n\n"), ("new line", "\n"))
_PUNCT_COMMANDS = (
    ("question mark", "?"),
    ("exclamation point", "!"),
    ("exclamation mark", "!"),
    ("full stop", "."),
    ("period", "."),
    ("comma", ","),
    ("colon", ":"),
)

# um, umm, uh, uhh, erm, hmm -- optionally wrapped in a comma / followed by a period.
_FILLER_RE = re.compile(r",?\s*\b(?:u+m+|u+h+|e+r+m+|h+m+)\b[,.]?", re.IGNORECASE)
# Em dash, en dash, double hyphen, or a hyphen with spaces on both sides.
_DASH_RE = re.compile(r"\s*(?:—|–|--)\s*|\s+-\s+")
_TRAILING_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3,}|…)\s*$")
_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3,}|…)\s*")
_SENTENCE_START_RE = re.compile(r"([.!?]\s+|\n)([a-z])")

# Words Whisper capitalises at the start of every utterance that are almost
# never proper nouns -- lowercased when the utterance continues a sentence.
_LOWER_STARTERS = frozenset(
    "a an and as at but by for from if in into is it its of on or so than that "
    "the then there these they this those to was we were what when where which "
    "while who with you".split()
)


def _phrase_pattern(phrase: str) -> str:
    return r"\b" + r"\s*".join(re.escape(w) for w in phrase.split()) + r"\b"


def _apply_replacements(text: str, replacements: Iterable[tuple[str, str]]) -> str:
    for heard, word in replacements:
        heard = heard.strip()
        if not heard or heard.lower() == word.lower():
            continue
        pattern = rf"(?<![\w']){re.escape(heard)}(?![\w'])"
        text = re.sub(pattern, lambda _m, w=word: w, text, flags=re.IGNORECASE)
    return text


def _apply_commands(text: str) -> str:
    for phrase, mark in _BREAK_COMMANDS:
        text = re.sub(rf"\s*{_phrase_pattern(phrase)}[{_PUNCT_CLASS}]?\s*",
                      mark, text, flags=re.IGNORECASE)
    for phrase, mark in _PUNCT_COMMANDS:
        text = re.sub(rf"[{_PUNCT_CLASS}]?\s*{_phrase_pattern(phrase)}[{_PUNCT_CLASS}]?",
                      mark, text, flags=re.IGNORECASE)
    return text


def _ellipsis(match: re.Match) -> str:
    following = match.string[match.end():match.end() + 1]
    return " " if following.islower() else ". "


def _tidy(text: str, final: bool = True) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(rf" +([{_PUNCT_CLASS}])", r"\1", text)
    text = re.sub(r",(?:\s*,)+", ",", text)
    text = re.sub(r",\s*([.;:!?])", r"\1", text)
    text = re.sub(r"([.;:!?]),", r"\1", text)
    text = re.sub(r"^[ ,]+", "", text)
    text = re.sub(r"[ ,]+$", "", text) if final else text.rstrip(" ")
    return text


def clean(text: str, replacements: Iterable[tuple[str, str]] = (), final: bool = True) -> str:
    """Tidy one transcription: replacements, spoken commands, fillers, dashes,
    ellipses, spacing, and capitalisation after sentence ends.

    With ``final=False`` (a chunk of a longer stream) trailing commas are kept.
    """
    text = _apply_replacements(text, replacements)
    text = _apply_commands(text)
    text = _FILLER_RE.sub("", text)
    text = _DASH_RE.sub(", ", text)
    text = _TRAILING_ELLIPSIS_RE.sub("", text)
    text = _ELLIPSIS_RE.sub(_ellipsis, text)
    text = _tidy(text, final)
    return _SENTENCE_START_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)


def _capitalise(text: str) -> str:
    return text[:1].upper() + text[1:]


def _soften(text: str) -> str:
    match = re.match(r"([A-Z][a-z']*)\b", text)
    if match and match.group(1).lower() in _LOWER_STARTERS:
        return text[:1].lower() + text[1:]
    return text


def join(text: str, before: str | None) -> str:
    """Fit cleaned ``text`` onto the text before the caret.

    ``before`` is what precedes the caret (only its tail matters), "" for an
    empty field, or None when it couldn't be read -- then we assume a fresh
    sentence and add no leading space.
    """
    if not text or text[0] == "\n":
        return text
    if before is None:
        return _capitalise(text)
    tail = before.rstrip(" \t")
    if tail == "" or tail[-1] in "\r\n":
        return _capitalise(text)
    if before[-1] in " \t" or before[-1] in _OPENERS or text[0] in _PUNCT:
        prefix = ""
    else:
        prefix = " "
    if tail[-1] in _SENTENCE_END:
        return prefix + _capitalise(text)
    return prefix + _soften(text)
