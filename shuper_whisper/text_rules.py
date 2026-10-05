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
# Marks a position where a spoken command ended a sentence or line, so the
# next word gets a capital. Never survives clean().
_CAP = "\x00"

# Spoken commands. "comma", "question mark", "exclamation point/mark" and
# "full stop" are always commands. "period", "colon", "new line" and "new
# paragraph" are also ordinary words ("trial period", "a new line of
# products"), so they only count when punctuation or the end of the text is
# next to them -- which is how Whisper writes a spoken command after a pause.
_BREAK_COMMANDS = (("new paragraph", "\n\n"), ("new line", "\n"))
_ALWAYS_COMMANDS = (
    ("question mark", "?"),
    ("exclamation point", "!"),
    ("exclamation mark", "!"),
    ("full stop", "."),
    ("comma", ","),
)
_AMBIGUOUS_COMMANDS = (("period", "."), ("colon", ":"))

# um, umm, uh, uhh, erm, hmm -- with an optional comma on either side and
# whatever punctuation followed it (handled in _drop_filler).
_FILLER_RE = re.compile(r",?\s*\b(?:u+m+|u+h+|e+r+m+|h+m+)\b(?!-)([,.!?]?)", re.IGNORECASE)
# Em dash, en dash, double hyphen, or a hyphen with spaces on both sides.
_DASH_RE = re.compile(r"\s*(?:—|–|--)\s*|\s+-\s+")
_TRAILING_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3,}|…)\s*$")
_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3,}|…)\s*")

# Words Whisper capitalises at the start of every utterance that are almost
# never proper nouns -- lowercased when the utterance continues a sentence.
_LOWER_STARTERS = frozenset(
    "a an and as at but by for from if in into is it its of on or so than that "
    "the then there these they this those to was we were what when where which "
    "while who with you".split()
)
# Too common to ever be a dictionary "sounds like" hint: replacing them would
# rewrite ordinary speech (e.g. training that heard silence as "you").
_COMMON_WORDS = _LOWER_STARTERS | frozenset(
    "i me my he she him her his our us your their them be been being am are "
    "have has had do does did not no yes yeah okay ok thank thanks please "
    "just like well oh hi hey hello bye".split()
)


def _phrase_pattern(phrase: str) -> str:
    return r"\b" + r"\s*".join(re.escape(w) for w in phrase.split()) + r"\b"


def _apply_replacements(text: str, replacements: Iterable[tuple[str, str]]) -> str:
    for heard, word in replacements:
        heard = heard.strip()
        if not heard or heard.lower() == word.lower() or len(heard) < 3:
            continue
        if all(w in _COMMON_WORDS for w in re.findall(r"[\w']+", heard.lower())):
            continue
        pattern = rf"(?<![\w']){re.escape(heard)}(?![\w'])"
        text = re.sub(pattern, lambda _m, w=word: w, text, flags=re.IGNORECASE)
    return text


def _apply_commands(text: str, final: bool = True, starts_clause: bool = True) -> str:
    # In a chunk of a longer stream (final=False) the end of the text is not
    # a pause, so it doesn't count as the edge of a command; nor is its start,
    # unless the text before it ended a clause.
    end = r"\s*$" if final else r"(?!)"
    start = "^|" if starts_clause else ""
    edge_before = rf"(?:{start}(?<=[{_PUNCT_CLASS}]))"
    for phrase, mark in _BREAK_COMMANDS:
        word = _phrase_pattern(phrase)
        pattern = (rf"(?:{edge_before}\s*{word}[{_PUNCT_CLASS}]?"
                   rf"|\s*{word}(?=[{_PUNCT_CLASS}]|{end})[{_PUNCT_CLASS}]?)\s*")
        text = re.sub(pattern, mark + _CAP, text, flags=re.IGNORECASE)
    for phrase, mark in _ALWAYS_COMMANDS:
        cap = _CAP if mark in _SENTENCE_END else ""
        text = re.sub(rf"[{_PUNCT_CLASS}]?\s*{_phrase_pattern(phrase)}[{_PUNCT_CLASS}]?",
                      mark + cap, text, flags=re.IGNORECASE)
    for phrase, mark in _AMBIGUOUS_COMMANDS:
        cap = _CAP if mark in _SENTENCE_END else ""
        word = _phrase_pattern(phrase)
        pattern = (rf"[{_PUNCT_CLASS}]\s*{word}[{_PUNCT_CLASS}]?"
                   rf"|\s*{word}(?:[{_PUNCT_CLASS}]|(?={end}))")
        text = re.sub(pattern, mark + cap, text, flags=re.IGNORECASE)
    return text


def _drop_filler(match: re.Match) -> str:
    trailing = match.group(1)
    if trailing in ("", ","):
        return ""
    # "good um." keeps its full stop; "Okay. Um." doesn't need a second one.
    before = match.string[:match.start()].rstrip()
    return "" if not before or before[-1] in _SENTENCE_END else trailing


def _ellipsis(match: re.Match) -> str:
    following = match.string[match.end():match.end() + 1]
    return " " if following.islower() else ". "


def _tidy(text: str, final: bool = True) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    # "word ," -> "word," but leave ".NET" and ".5" alone.
    text = re.sub(rf" +([{_PUNCT_CLASS}])(?=[\s{_CAP}]|$)", r"\1", text)
    text = re.sub(r",(?:\s*,)+", ",", text)
    text = re.sub(r",\s*([.;:!?])", r"\1", text)
    text = re.sub(r"([.;:!?]),", r"\1", text)
    text = re.sub(r"^[ ,]+", "", text)
    text = re.sub(r"[ ,]+$", "", text) if final else text.rstrip(" ")
    return text


def _capitalise_after_commands(text: str) -> str:
    # Whisper already capitalises real sentences; only words after a spoken
    # command need it. ("3 p.m. today" must stay lowercase.)
    text = re.sub(rf"{_CAP}(\s*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    return text.replace(_CAP, "")


def clean(text: str, replacements: Iterable[tuple[str, str]] = (), final: bool = True,
          starts_clause: bool = True) -> str:
    """Tidy one transcription: replacements, spoken commands, fillers, dashes,
    ellipses, spacing, and capitalisation after spoken sentence ends.

    With ``final=False`` (a chunk of a longer stream) trailing commas are kept.
    ``starts_clause=False`` says the chunk continues a sentence mid-clause.
    """
    text = _apply_replacements(text, replacements)
    text = _apply_commands(text, final, starts_clause)
    text = _FILLER_RE.sub(_drop_filler, text)
    text = _DASH_RE.sub(", ", text)
    text = _TRAILING_ELLIPSIS_RE.sub("", text)
    text = _ELLIPSIS_RE.sub(_ellipsis, text)
    text = _tidy(text, final)
    return _capitalise_after_commands(text)


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
