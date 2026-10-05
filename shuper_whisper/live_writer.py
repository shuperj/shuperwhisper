"""Types a live transcription into the focused field and revises its own tail.

The field holds: <before><committed><tail>. ``before`` was there when we
attached, ``committed`` is cleaned stable text we typed, and ``tail`` is
tentative text we may still rewrite with backspaces.

We only ever backspace over our own tail, and only while it is provably
still ours: same field, no physical keyboard/mouse input since our last
write, and (when UIA can read it) the text before the caret still ends with
what we typed. Otherwise we *freeze*: the old field keeps whatever it has and
we re-attach at the current caret -- macOS-style "just click back in".
"""

import re
from typing import Callable, Iterable, Optional

from . import uia
from ._win32_keys import send_text, wait_for_modifiers_released
from .caret import field_id as current_field_id
from .input_monitor import InputMonitor
from .text_rules import clean, join

# Words that may start or be a spoken command. Held back while the next word
# is unknown, so "new" + "line" can still become a newline and a trailing
# "period" can be judged once we know whether a pause followed it.
_HOLD_BACK = frozenset({"new", "question", "exclamation", "full", "period", "colon"})
_CHECK_CHARS = 50


def _norm(word: str) -> str:
    return re.sub(r"[^\w']", "", word).lower()


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _drop_words(text: str, skip: list[str]) -> tuple[str, list[str]]:
    """Remove leading words already left behind in a previous field."""
    words = text.split()
    while skip and words:
        if _norm(words[0]) != skip[0]:
            return " ".join(words), []
        words.pop(0)
        skip = skip[1:]
    return " ".join(words), skip


def _without_fragment(tentative: str) -> str:
    """Whisper marks a cut-off word with a trailing hyphen ("f-"); don't show it."""
    words = tentative.split()
    if words and words[-1].endswith("-"):
        words.pop()
    return " ".join(words)


class LiveWriter:
    def __init__(self, send: Callable[..., None] = send_text,
                 read_context: Callable[[], Optional[str]] = uia.text_before_caret,
                 field_id: Callable[[], object] = current_field_id,
                 monitor_factory: Callable[..., InputMonitor] = InputMonitor,
                 replacements: Callable[[], Iterable[tuple[str, str]]] = lambda: (),
                 wait_modifiers: Callable[[], bool] = wait_for_modifiers_released):
        self._send = send
        self._read_context = read_context
        self._field_id = field_id
        self._monitor_factory = monitor_factory
        self._replacements = replacements
        self._wait_modifiers = wait_modifiers
        self._monitor = None
        self._field = None
        self._before: Optional[str] = None
        self._committed = ""
        self._tail = ""
        self._pending = ""          # held-back stable word
        self._skip: list[str] = []  # words left in a field we froze out of
        self._last_field = None     # across sessions: fallback context when UIA can't read
        self._last_text = ""

    # -- session ---------------------------------------------------------------

    def begin(self, ignore_vks: Iterable[int] = ()) -> None:
        self._wait_modifiers()
        self._monitor = self._monitor_factory(ignore_vks=ignore_vks)
        self._monitor.start()
        self._pending, self._skip = "", []
        self._attach()

    def finish(self) -> None:
        if self._monitor:
            self._monitor.stop()
            self._monitor = None
        self._last_field = self._field
        self._last_text = ((self._before or "") + self._committed + self._tail)[-200:]

    def _attach(self) -> None:
        self._field = self._field_id()
        before = self._read_context()
        if before is None and self._field == self._last_field and self._last_text:
            before = self._last_text
        self._before = before
        self._committed = ""
        self._tail = ""
        if self._monitor:
            self._monitor.clear()

    def _context(self) -> Optional[str]:
        if self._before is None and not self._committed:
            return None
        return (self._before or "") + self._committed

    def _still_ours(self) -> bool:
        if self._monitor and self._monitor.user_input:
            return False
        if self._field_id() != self._field:
            return False
        if not self._tail:
            return True
        actual = self._read_context()
        if actual is None:
            return True
        expected = ((self._before or "") + self._committed + self._tail).replace("\r", "")
        actual = actual.replace("\r", "")
        n = min(len(expected), len(actual), _CHECK_CHARS)
        return actual[-n:] == expected[-n:]

    # -- updates -----------------------------------------------------------------

    def update(self, stable_delta: str, tentative: str, final: bool = False) -> None:
        stable = f"{self._pending} {stable_delta}".strip()
        self._pending = ""
        if not final:
            words = stable.split()
            if words and _norm(words[-1]) in _HOLD_BACK:
                self._pending = words[-1]
                stable = " ".join(words[:-1])
                tentative = f"{self._pending} {tentative}".strip()
        tentative = _without_fragment(tentative)

        if not self._still_ours():
            self._skip = [_norm(w) for w in self._tail.split()]
            self._attach()
        if self._skip:
            stable, self._skip = _drop_words(stable, self._skip)
            if self._skip:
                tentative, _ = _drop_words(tentative, list(self._skip))

        replacements = list(self._replacements())
        context = self._context()
        new_stable = join(clean(stable, replacements, final=final), context) if stable else ""
        tail_context = context if not new_stable else (context or "") + new_stable
        new_tail = ""
        if tentative and not final:
            new_tail = join(clean(tentative, replacements, final=False), tail_context)

        target = new_stable + new_tail
        common = _common_prefix(self._tail, target)
        backspaces = len(self._tail) - common
        if backspaces or target[common:]:
            self._send(target[common:], backspaces=backspaces)
        self._committed += new_stable
        self._tail = new_tail
