# Stage 2 — Live inline dictation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (run inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Words appear in the focused field while you speak and the still-changing tail corrects itself in place, like macOS dictation. If you click into another field mid-dictation, the first field is left alone and dictation continues in the new one.

**Architecture:**
- **Streaming.** A `StreamingSession` thread re-transcribes the current utterance about every 400 ms (GPU) or 1 s (CPU).
  - LocalAgreement-2 splits each hypothesis into *stable* words and a *tentative* tail.
  - Silero VAD ends an utterance after 0.7 s of silence.
- **Writing.** A `LiveWriter` turns each hypothesis into backspaces plus new text, touching only its own tail.
  - Before any backspace it checks that the field is unchanged and that no physical keyboard or mouse input has happened. If either check fails, it freezes and re-attaches at the new caret.
- **Indicator.** A small pill sits under the text caret.

**Tech Stack:** Python 3.12, faster-whisper (Silero VAD in `faster_whisper.vad`), Win32 low-level hooks via ctypes, UI Automation via comtypes, pywebview.

**Spec:** `docs/superpowers/specs/2026-10-04-live-dictation-design.md` (Stage 2 section)

**Depends on:** Stage 1 merged, specifically `text_rules`, `audio.AudioRecorder`, `transcriber.Transcriber`, `_win32_keys.send_text` / `InjectionBlocked` / `SHUPER_INPUT_TAG`, `uia`, and the toggle `HotkeyManager`.

## Global Constraints

- Windows 10/11 x64. Never touch the clipboard.
- The writer never sends more backspaces than the length of its own visible tail.
- Low-level hooks run **only while dictating**.
- Re-decode interval: 0.4 s on GPU, 1.0 s on CPU. It stretches to 1.2× the last decode time if decodes are slower.
- An utterance ends after 0.7 s of silence. Hard cap: 25 s. Auto-stop after 30 s with no speech.
- Tests: `python -m pytest tests/ -q`, run before every commit.
- Conventional commits ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Branch: `feat/stage2-live-dictation`, off `main` after stage 1 merges. One PR on Gitea; never merge it.

---

### Task 0: Branch

- [ ] **Step 1**

```bash
cd D:/dev/hobby/projects/shuperwhisper && git checkout main && git pull && git checkout -b feat/stage2-live-dictation
```

---

### Task 1: Streaming primitives

**Files:**
- Modify: `shuper_whisper/text_rules.py`, `shuper_whisper/audio.py`, `shuper_whisper/transcriber.py`
- Test: `tests/test_text_rules.py`, `tests/test_audio.py`, `tests/test_transcriber.py`

**Interfaces:**
- Produces: `clean(text, replacements=(), final=True)`. When `final=False`, a trailing comma or colon is kept, because more words follow.
- Produces: `AudioRecorder.read_new() -> np.ndarray`, the 16 kHz audio captured since the previous call.
- Produces: `Transcriber.transcribe_words(audio, initial_prompt=None, hotwords=None, beam_size=1) -> list[str]`

- [ ] **Step 1: Failing tests**

Append to `tests/test_text_rules.py`:

```python
class TestPartial:
    def test_partial_keeps_trailing_comma(self):
        assert clean("I think,", final=False) == "I think,"

    def test_final_drops_trailing_comma(self):
        assert clean("I think,") == "I think"

    def test_partial_dash_becomes_trailing_comma(self):
        assert clean("I went home —", final=False) == "I went home,"
```

Append to `tests/test_audio.py`, inside `class TestCapture`:

```python
    def test_read_new_returns_only_fresh_audio(self, device_info):
        streams = []
        r = make(streams)
        r.start_recording()
        streams[0].feed(sine(48000, 0.3))
        first = r.read_new()
        assert abs(len(first) - 4800) < 400
        assert len(r.read_new()) == 0
        streams[0].feed(sine(48000, 0.3))
        assert len(r.read_new()) > 0
```

Append to `tests/test_transcriber.py`:

```python
def test_transcribe_words_is_greedy_and_split():
    t = loaded([" Hello there,", " friend."])
    assert t.transcribe_words(np.zeros(16000, np.float32)) == ["Hello", "there,", "friend."]
    assert t._model.kwargs["beam_size"] == 1
    assert t._model.kwargs["vad_filter"] is False
```

Run: `python -m pytest tests/test_text_rules.py tests/test_audio.py tests/test_transcriber.py -q`
Expected: three FAILs (unknown keyword `final`, no `read_new`, no `transcribe_words`).

- [ ] **Step 2: Implement**

In `text_rules.py`:
- Change `_tidy(text: str)` to `_tidy(text: str, final: bool = True)`.
- Replace its last line (`text = re.sub(r"[ ,]+$", "", text)`) with:

```python
    text = re.sub(r"[ ,]+$", "", text) if final else text.rstrip(" ")
```

- Change `clean`'s signature to `clean(text, replacements=(), final=True)`.
- Pass `final` to `_tidy(text, final)`.
- Extend its docstring with: ``With ``final=False`` (a chunk of a longer stream) trailing commas are kept.``

In `audio.py`, add `self._read_pos = 0` to `__init__`. Set `self._read_pos = 0` inside the `with self._lock:` block in `start_recording`. Then add:

```python
    def read_new(self) -> np.ndarray:
        """16 kHz audio captured since the previous call (for live decoding)."""
        with self._lock:
            fresh = self._chunks[self._read_pos:]
            self._read_pos = len(self._chunks)
        return np.concatenate(fresh) if fresh else np.zeros(0, np.float32)
```

In `transcriber.py`, add to `Transcriber`:

```python
    def transcribe_words(self, audio: np.ndarray, initial_prompt: Optional[str] = None,
                         hotwords: Optional[str] = None, beam_size: int = 1) -> list[str]:
        """Fast pass for live dictation: words of the whole buffer.

        No VAD filter here -- StreamingSession already segments by speech.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        kwargs = {
            "beam_size": beam_size,
            "language": None if self._language == "auto" else self._language,
            "vad_filter": False,
            "condition_on_previous_text": False,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        if hotwords:
            kwargs["hotwords"] = hotwords
        segments, _info = self._model.transcribe(audio, **kwargs)
        return " ".join(s.text.strip() for s in segments).split()
```

- [ ] **Step 3: Run the tests**

Run: `python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add shuper_whisper/text_rules.py shuper_whisper/audio.py shuper_whisper/transcriber.py tests/
git commit -m "feat: streaming primitives (partial clean, read_new, greedy word pass)"
```

---

### Task 2: Streaming session (LocalAgreement + VAD utterances)

**Files:**
- Create: `shuper_whisper/streaming.py`
- Test: `tests/test_streaming.py`

**Interfaces:**
- Consumes: `Transcriber.transcribe_words`, `AudioRecorder.read_new`
- Produces: `Hypothesis(stable_delta: str, tentative: str, final: bool)`
- Produces: `LocalAgreement` with `.update(words) -> (newly_stable, tentative)` and `.flush(words=None) -> list[str]`
- Produces: `StreamingSession(transcriber, read_audio, on_hypothesis, on_finished, on_auto_stop, prompt=lambda: "", hotwords=None, interval=0.4, speech_spans=silero_speech_spans, clock=time.monotonic)` with `.start()`, `.stop()`, `.join(timeout)` and `._run()`. `on_finished(error: str | None)` is always called exactly once.

- [ ] **Step 1: Write `tests/test_streaming.py`**

```python
"""Tests for LocalAgreement and StreamingSession, with scripted decodes."""

import numpy as np

from shuper_whisper.streaming import SAMPLE_RATE, Hypothesis, LocalAgreement, StreamingSession

SR = SAMPLE_RATE


class TestLocalAgreement:
    def test_first_hypothesis_is_all_tentative(self):
        la = LocalAgreement()
        assert la.update(["send", "the"]) == ([], ["send", "the"])

    def test_common_prefix_becomes_stable(self):
        la = LocalAgreement()
        la.update(["send", "the"])
        assert la.update(["send", "the", "report"]) == (["send", "the"], ["report"])

    def test_punctuation_and_case_ignored_for_agreement(self):
        la = LocalAgreement()
        la.update(["Send", "the"])
        newly, tentative = la.update(["send,", "the", "report"])
        assert newly == ["send,", "the"] and tentative == ["report"]

    def test_stable_never_shrinks(self):
        la = LocalAgreement()
        la.update(["a", "b", "c"])
        la.update(["a", "b", "c", "d"])
        assert la.update(["a", "x"]) == ([], [])

    def test_flush_returns_rest(self):
        la = LocalAgreement()
        la.update(["a", "b"])
        la.update(["a", "b", "c"])
        assert la.flush(["a", "b", "c", "d"]) == ["c", "d"]
        assert la.update(["new"]) == ([], ["new"])

    def test_flush_without_words_uses_last_hypothesis(self):
        la = LocalAgreement()
        la.update(["a", "b"])
        assert la.flush() == ["a", "b"]


class FakeTranscriber:
    def __init__(self, decodes):
        self.decodes = list(decodes)
        self.calls = []

    def transcribe_words(self, audio, initial_prompt=None, hotwords=None, beam_size=1):
        self.calls.append((len(audio), initial_prompt, beam_size))
        return self.decodes.pop(0) if self.decodes else []


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def run(ticks, decodes, prompt=""):
    """ticks: list of (seconds_of_new_audio, speech_spans_in_samples)."""
    clock = Clock()
    hyps, finished, auto = [], [], []
    plan = list(ticks)
    state = {"spans": []}

    def read_audio():
        if not plan:
            session.stop()
            return np.zeros(0, np.float32)
        secs, spans = plan.pop(0)
        state["spans"] = spans
        clock.t += 0.4
        return np.full(int(secs * SR), 0.1, np.float32)

    session = StreamingSession(
        transcriber=FakeTranscriber(decodes), read_audio=read_audio,
        on_hypothesis=hyps.append, on_finished=finished.append,
        on_auto_stop=lambda: auto.append(True), prompt=lambda: prompt,
        interval=0.0, speech_spans=lambda audio: state["spans"], clock=clock)
    session._run()
    return session, hyps, finished, auto


def test_words_stream_then_finalize_on_silence():
    ticks = [
        (0.4, [(0, 6400)]),
        (0.4, [(0, 12800)]),
        (0.8, [(0, 12800)]),          # 0.8 s silence after speech -> utterance ends
    ]
    decodes = [["send", "the"], ["send", "the", "report"], ["Send", "the", "report."]]
    _s, hyps, finished, _ = run(ticks, decodes)
    assert hyps[0] == Hypothesis("", "send the", False)
    assert hyps[1] == Hypothesis("send the", "report", False)
    assert hyps[2] == Hypothesis("report.", "", True)
    assert finished == [None]


def test_no_speech_emits_nothing_and_final_is_quiet():
    _s, hyps, finished, _ = run([(0.4, []), (0.4, [])], [])
    assert hyps == [Hypothesis("", "", True)] and finished == [None]


def test_stop_mid_utterance_does_final_beam_pass():
    ticks = [(0.4, [(0, 6400)])]
    decodes = [["hello"], ["Hello", "world."]]
    s, hyps, finished, _ = run(ticks, decodes)
    assert hyps[-1] == Hypothesis("Hello world.", "", True)
    assert s._transcriber.calls[-1][2] == 5


def test_prompt_includes_dictionary_and_committed_text():
    ticks = [(0.4, [(0, 6400)]), (0.8, [(0, 6400)]), (0.4, [(0, 6400)])]
    decodes = [["one"], ["One."], ["two"]]
    s, _h, _f, _a = run(ticks, decodes, prompt="Vocabulary: Dana.")
    assert s._transcriber.calls[2][1] == "Vocabulary: Dana. One."


def test_auto_stop_after_30s_without_speech():
    ticks = [(0.4, [])] * 80                # 80 * 0.4 s = 32 s of silence
    _s, _h, _f, auto = run(ticks, [])
    assert auto == [True]


def test_transcriber_error_reaches_on_finished():
    class Boom(FakeTranscriber):
        def transcribe_words(self, *a, **k):
            raise RuntimeError("CUDA out of memory")
    finished = []
    s = StreamingSession(transcriber=Boom([]), read_audio=lambda: np.full(SR, 0.1, np.float32),
                         on_hypothesis=lambda h: None, on_finished=finished.append,
                         on_auto_stop=lambda: None, interval=0.0,
                         speech_spans=lambda a: [(0, len(a))])
    s._run()
    assert finished == ["CUDA out of memory"]
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_streaming.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `shuper_whisper/streaming.py`**

```python
"""Live decoding: re-transcribe the current utterance every few hundred ms.

LocalAgreement-2: a word is *stable* once two consecutive hypotheses agree on
it (and everything before it). Stable words are committed; the rest of the
newest hypothesis is a *tentative* tail the writer may still rewrite.

Utterances are bounded by Silero VAD: after END_SILENCE of quiet, everything
is committed and the buffer restarts, so each decode stays short.
"""

import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Hypothesis:
    stable_delta: str   # newly committed text
    tentative: str      # current unstable tail (replaces the previous tail)
    final: bool = False  # utterance ended; nothing is tentative


def _norm(word: str) -> str:
    return re.sub(r"[^\w']", "", word).lower()


class LocalAgreement:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._prev: list[str] = []
        self._stable = 0

    def update(self, words: list[str]) -> tuple[list[str], list[str]]:
        """Returns (newly stable words, tentative words)."""
        agree = 0
        for a, b in zip(self._prev, words):
            if _norm(a) != _norm(b):
                break
            agree += 1
        self._prev = words
        newly: list[str] = []
        if agree > self._stable:
            newly = words[self._stable:agree]
            self._stable = agree
        return newly, words[self._stable:]

    def flush(self, words: Optional[list[str]] = None) -> list[str]:
        """End of utterance: everything not yet stable becomes stable."""
        words = self._prev if words is None else words
        rest = words[self._stable:]
        self.reset()
        return rest


def silero_speech_spans(audio: np.ndarray) -> list[tuple[int, int]]:
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    options = VadOptions(min_silence_duration_ms=300, speech_pad_ms=100)
    return [(s["start"], s["end"]) for s in get_speech_timestamps(audio, options)]


class StreamingSession:
    END_SILENCE = 0.7
    MAX_UTTERANCE = 25.0
    AUTO_STOP = 30.0
    PROMPT_CHARS = 200

    def __init__(self, transcriber, read_audio: Callable[[], np.ndarray],
                 on_hypothesis: Callable[[Hypothesis], None],
                 on_finished: Callable[[Optional[str]], None],
                 on_auto_stop: Callable[[], None],
                 prompt: Callable[[], str] = lambda: "",
                 hotwords: Optional[str] = None,
                 interval: float = 0.4,
                 speech_spans: Callable[[np.ndarray], list] = silero_speech_spans,
                 clock: Callable[[], float] = time.monotonic):
        self._transcriber = transcriber
        self._read_audio = read_audio
        self._on_hypothesis = on_hypothesis
        self._on_finished = on_finished
        self._on_auto_stop = on_auto_stop
        self._prompt_fn = prompt
        self._hotwords = hotwords
        self._base_interval = interval
        self._interval = interval
        self._speech_spans = speech_spans
        self._clock = clock
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._agreement = LocalAgreement()
        self._buffer = np.zeros(0, np.float32)
        self._committed = ""
        self._last_tentative = ""
        self._last_speech = clock()
        self._auto_stopped = False

    # -- control ---------------------------------------------------------------

    def start(self) -> None:
        self._last_speech = self._clock()
        self._thread = threading.Thread(target=self._run, daemon=True, name="streaming")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    # -- internals ---------------------------------------------------------------

    def _prompt(self) -> Optional[str]:
        parts = [self._prompt_fn() or "", self._committed.strip()[-self.PROMPT_CHARS:]]
        return " ".join(p for p in parts if p) or None

    def _decode(self, beam_size: int = 1) -> list[str]:
        started = self._clock()
        words = self._transcriber.transcribe_words(
            self._buffer, initial_prompt=self._prompt(), hotwords=self._hotwords,
            beam_size=beam_size)
        self._interval = max(self._base_interval, (self._clock() - started) * 1.2)
        return words

    def _emit(self, newly: list[str], tentative: list[str], final: bool = False) -> None:
        stable_text, tentative_text = " ".join(newly), " ".join(tentative)
        if not final and not stable_text and tentative_text == self._last_tentative:
            return
        self._last_tentative = tentative_text
        if stable_text:
            self._committed += " " + stable_text
        self._on_hypothesis(Hypothesis(stable_text, tentative_text, final))

    def _append_audio(self) -> list:
        chunk = self._read_audio()
        if len(chunk):
            self._buffer = np.concatenate([self._buffer, chunk])
        return self._speech_spans(self._buffer) if len(self._buffer) else []

    def _tick(self) -> None:
        spans = self._append_audio()
        if self._stop.is_set():
            return  # the final pass in _run() decodes what's left
        now = self._clock()
        if not spans:
            if len(self._buffer) > 2 * SAMPLE_RATE:
                self._buffer = self._buffer[-SAMPLE_RATE // 2:]
            if not self._auto_stopped and now - self._last_speech >= self.AUTO_STOP:
                self._auto_stopped = True
                self._on_auto_stop()
            return
        speech_end = spans[-1][1]
        silence_after = (len(self._buffer) - speech_end) / SAMPLE_RATE
        self._last_speech = now - silence_after
        words = self._decode()
        too_long = len(self._buffer) >= self.MAX_UTTERANCE * SAMPLE_RATE
        if silence_after >= self.END_SILENCE or too_long:
            self._emit(self._agreement.flush(words), [], final=True)
            self._buffer = self._buffer[len(self._buffer) if too_long else speech_end:]
        else:
            newly, tentative = self._agreement.update(words)
            self._emit(newly, tentative)

    def _run(self) -> None:
        error: Optional[str] = None
        try:
            while not self._stop.wait(self._interval):
                self._tick()
            spans = self._append_audio()
            if spans:
                self._emit(self._agreement.flush(self._decode(beam_size=5)), [], final=True)
            else:
                self._emit(self._agreement.flush(), [], final=True)
        except Exception as e:
            error = str(e)
        finally:
            self._on_finished(error)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_streaming.py -q`
Expected: PASS. If `test_words_stream_then_finalize_on_silence` fails, trace through `_tick` by hand and correct the code. The test's expectations come straight from the spec.

- [ ] **Step 5: Commit**

```bash
git add shuper_whisper/streaming.py tests/test_streaming.py
git commit -m "feat(streaming): LocalAgreement-2 live decoding with VAD-bounded utterances"
```

---

### Task 3: Field identity, caret position and the input monitor

**Files:**
- Create: `shuper_whisper/caret.py`, `shuper_whisper/input_monitor.py`
- Modify: `shuper_whisper/uia.py` (add `caret_bounds`)
- Test: `tests/test_caret.py`, `tests/test_input_monitor.py`

**Interfaces:**
- Produces in `caret.py`: `field_id() -> tuple`, `caret_rect(use_uia: bool = False) -> tuple[int, int, int, int] | None` (screen left, top, right, bottom), `foreground_rect() -> tuple | None`, and `place_below(caret, work_area, size, gap) -> tuple[int, int]`.
- Produces in `uia.py`: `caret_bounds(timeout=0.15) -> tuple[int, int, int, int] | None`.
- Produces in `input_monitor.py`: `InputMonitor(ignore_vks=())` with `.start()`, `.stop()`, `.clear()`, `.user_input`, `._on_key(vk, flags)` and `._on_mouse(msg, flags)`.

- [ ] **Step 1: Write `tests/test_caret.py`**

```python
from shuper_whisper.caret import place_below

WORK = (0, 0, 1920, 1040)


def test_places_under_caret():
    assert place_below((500, 300, 502, 320), WORK, (100, 32), 6) == (494, 326)


def test_flips_above_near_bottom():
    assert place_below((500, 1020, 502, 1038), WORK, (100, 32), 6) == (494, 982)


def test_clamps_to_right_edge():
    assert place_below((1900, 300, 1902, 320), WORK, (100, 32), 6) == (1820, 326)


def test_clamps_to_left_edge_on_secondary_monitor():
    assert place_below((-1918, 300, -1916, 320), (-1920, 0, 0, 1040), (100, 32), 6) == (-1920, 326)
```

- [ ] **Step 2: Write `tests/test_input_monitor.py`**

```python
from shuper_whisper.input_monitor import (
    LLKHF_INJECTED, LLMHF_INJECTED, WM_LBUTTONDOWN, WM_MOUSEMOVE, InputMonitor,
)


def test_physical_key_flags_input():
    m = InputMonitor()
    m._on_key(0x41, 0)
    assert m.user_input


def test_injected_key_ignored():
    m = InputMonitor()
    m._on_key(0x41, LLKHF_INJECTED)
    assert not m.user_input


def test_hotkey_keys_ignored():
    m = InputMonitor(ignore_vks=(0xA2, 0x20))
    m._on_key(0x20, 0)
    m._on_key(0xA2, 0)
    assert not m.user_input


def test_click_flags_input_but_move_does_not():
    m = InputMonitor()
    m._on_mouse(WM_MOUSEMOVE, 0)
    assert not m.user_input
    m._on_mouse(WM_LBUTTONDOWN, 0)
    assert m.user_input


def test_injected_click_ignored_and_clear_resets():
    m = InputMonitor()
    m._on_mouse(WM_LBUTTONDOWN, LLMHF_INJECTED)
    assert not m.user_input
    m._on_key(0x41, 0)
    m.clear()
    assert not m.user_input
```

Run: `python -m pytest tests/test_caret.py tests/test_input_monitor.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `shuper_whisper/caret.py`**

```python
"""Where is the text caret, and which field has focus?"""

import ctypes
import ctypes.wintypes as wt

from . import uia

user32 = ctypes.windll.user32


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND),
                ("hwndFocus", wt.HWND), ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND),
                ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]


def _gui_info() -> tuple[int, _GUITHREADINFO | None]:
    foreground = user32.GetForegroundWindow()
    if not foreground:
        return 0, None
    thread_id = user32.GetWindowThreadProcessId(foreground, None)
    info = _GUITHREADINFO(cbSize=ctypes.sizeof(_GUITHREADINFO))
    if not user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        return foreground, None
    return foreground, info


def field_id() -> tuple:
    """(focused HWND, UIA RuntimeId). Browsers share one HWND across all their
    fields, so the UIA id is what tells two fields on a page apart."""
    foreground, info = _gui_info()
    hwnd = (info.hwndFocus if info and info.hwndFocus else foreground) or 0
    return (int(hwnd), uia.focused_element_id())


def caret_rect(use_uia: bool = False):
    """Screen rect of the caret, from Win32 (classic controls) or UIA."""
    _foreground, info = _gui_info()
    if info and info.hwndCaret:
        rc = info.rcCaret
        top_left = wt.POINT(rc.left, rc.top)
        bottom_right = wt.POINT(rc.right, rc.bottom)
        user32.ClientToScreen(info.hwndCaret, ctypes.byref(top_left))
        user32.ClientToScreen(info.hwndCaret, ctypes.byref(bottom_right))
        return (top_left.x, top_left.y, max(bottom_right.x, top_left.x + 1), bottom_right.y)
    return uia.caret_bounds() if use_uia else None


def foreground_rect():
    foreground = user32.GetForegroundWindow()
    rect = wt.RECT()
    if foreground and user32.GetWindowRect(foreground, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


def place_below(caret, work_area, size, gap):
    """Top-left for a box of ``size`` just under ``caret``, kept on screen."""
    left, top, _right, bottom = caret
    wa_left, wa_top, wa_right, wa_bottom = work_area
    width, height = size
    x = min(max(left - gap, wa_left), wa_right - width)
    y = bottom + gap
    if y + height > wa_bottom:
        y = top - height - gap
    return x, max(y, wa_top)
```

- [ ] **Step 4: Add `caret_bounds` to `shuper_whisper/uia.py`**

```python
def _caret_bounds():
    uia, mod = _client()
    element = uia.GetFocusedElement()
    if not element:
        return None
    pattern = element.GetCurrentPattern(_UIA_TEXT_PATTERN_ID)
    if not pattern:
        return None
    selection = pattern.QueryInterface(mod.IUIAutomationTextPattern).GetSelection()
    if not selection or selection.Length == 0:
        return None
    rng = selection.GetElement(0).Clone()
    # A collapsed range usually has no rectangle; measure the character before it.
    rng.MoveEndpointByRange(mod.TextPatternRangeEndpoint_End, rng, mod.TextPatternRangeEndpoint_Start)
    rng.MoveEndpointByUnit(mod.TextPatternRangeEndpoint_Start, mod.TextUnit_Character, -1)
    rects = list(rng.GetBoundingRectangles() or ())
    if len(rects) < 4:
        return None
    left, top, width, height = rects[-4:]
    right = int(left + width)
    return (right, int(top), right + 1, int(top + height))


def caret_bounds(timeout: float = 0.15):
    """Screen rect just after the character before the caret, or None."""
    return _run(_caret_bounds, timeout)
```

- [ ] **Step 5: Create `shuper_whisper/input_monitor.py`**

```python
"""Notice the user's own keyboard/mouse input while dictation is typing.

Low-level hooks are installed only for the length of a dictation session.
Events we injected ourselves (SendInput) carry the INJECTED flag and are
ignored, as are the hotkey's own keys.
"""

import ctypes
import ctypes.wintypes as wt
import threading
from typing import Iterable, Optional

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01
_CLICKS = (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN)


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, _HOOKPROC, wt.HINSTANCE, wt.DWORD)
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = (ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)


class InputMonitor:
    def __init__(self, ignore_vks: Iterable[int] = ()):
        self._ignore = frozenset(ignore_vks)
        self._user_input = False
        self._thread: Optional[threading.Thread] = None
        self._thread_id = 0
        self._ready = threading.Event()
        # Keep the ctypes callbacks alive for as long as the hooks are installed.
        self._kb_proc = _HOOKPROC(self._keyboard_hook)
        self._mouse_proc = _HOOKPROC(self._mouse_hook)

    # Pure handlers (unit-tested) ------------------------------------------------

    def _on_key(self, vk: int, flags: int) -> None:
        if not flags & LLKHF_INJECTED and vk not in self._ignore:
            self._user_input = True

    def _on_mouse(self, message: int, flags: int) -> None:
        if message in _CLICKS and not flags & LLMHF_INJECTED:
            self._user_input = True

    # Hook plumbing ----------------------------------------------------------------

    def _keyboard_hook(self, code, wparam, lparam):
        if code >= 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            info = ctypes.cast(lparam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            self._on_key(info.vkCode, info.flags)
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _mouse_hook(self, code, wparam, lparam):
        if code >= 0 and wparam in _CLICKS:
            info = ctypes.cast(lparam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
            self._on_mouse(wparam, info.flags)
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _loop(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        module = kernel32.GetModuleHandleW(None)
        kb = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, module, 0)
        mouse = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, module, 0)
        self._ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        for hook in (kb, mouse):
            if hook:
                user32.UnhookWindowsHookEx(hook)

    def start(self) -> None:
        if self._thread:
            return
        self._user_input = False
        self._ready.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="input-monitor")
        self._thread.start()
        self._ready.wait(1.0)

    def stop(self) -> None:
        if not self._thread:
            return
        user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(1.0)
        self._thread = None

    def clear(self) -> None:
        self._user_input = False

    @property
    def user_input(self) -> bool:
        return self._user_input
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_caret.py tests/test_input_monitor.py -q`
Expected: PASS.

- [ ] **Step 7: Live smoke test of the hooks**

```bash
python -c "
import time; from shuper_whisper.input_monitor import InputMonitor
m=InputMonitor(); m.start(); print('click or type within 3s'); time.sleep(3); print('user_input =', m.user_input); m.stop()"
```

Expected: `user_input = True` after a click, and the command exits cleanly.

- [ ] **Step 8: Commit**

```bash
git add shuper_whisper/caret.py shuper_whisper/input_monitor.py shuper_whisper/uia.py tests/test_caret.py tests/test_input_monitor.py
git commit -m "feat: caret/field detection and a session-scoped physical-input monitor"
```

---

### Task 4: Live writer

**Files:**
- Create: `shuper_whisper/live_writer.py`
- Delete: `shuper_whisper/injector.py`, `tests/test_injector.py`
- Test: `tests/test_live_writer.py`

**Interfaces:**
- Consumes: `text_rules.clean/join`, `_win32_keys.send_text` / `wait_for_modifiers_released`, `uia.text_before_caret`, `caret.field_id` and `InputMonitor`.
- Produces: `LiveWriter(send=send_text, read_context=uia.text_before_caret, field_id=caret.field_id, monitor_factory=InputMonitor, replacements=lambda: (), wait_modifiers=wait_for_modifiers_released)`.
  - `.begin(ignore_vks=())` starts a session.
  - `.update(stable_delta, tentative, final=False)` applies a hypothesis.
  - `.finish()` ends the session.

- [ ] **Step 1: Write `tests/test_live_writer.py`**

```python
"""LiveWriter against a simulated text field."""

from shuper_whisper.live_writer import LiveWriter


class Field:
    """A text box: send() applies backspaces then appends, like SendInput would."""

    def __init__(self, text="", readable=True):
        self.text = text
        self.readable = readable
        self.backspaces = 0

    def send(self, text, backspaces=0):
        self.backspaces += backspaces
        if backspaces:
            self.text = self.text[:-backspaces]
        self.text += text

    def context(self):
        return self.text[-200:] if self.readable else None


class Monitor:
    def __init__(self, ignore_vks=()):
        self.user_input = False

    def start(self): pass
    def stop(self): pass
    def clear(self): self.user_input = False


class Env:
    def __init__(self, text="", readable=True):
        self.fields = {"a": Field(text, readable)}
        self.focus = "a"
        self.monitor = Monitor()
        self.writer = LiveWriter(
            send=lambda t, backspaces=0: self.fields[self.focus].send(t, backspaces),
            read_context=lambda: self.fields[self.focus].context(),
            field_id=lambda: self.focus,
            monitor_factory=lambda ignore_vks=(): self.monitor,
            replacements=lambda: [("mackinaw", "Mackinac")],
            wait_modifiers=lambda: True,
        )

    @property
    def field(self):
        return self.fields[self.focus]


def test_tentative_then_stable_rewrites_only_the_tail():
    env = Env()
    w = env.writer
    w.begin()
    w.update("", "send the")
    assert env.field.text == "Send the"
    w.update("send the", "report")
    assert env.field.text == "Send the report"
    w.update("", "reports to")
    assert env.field.text == "Send the reports to"
    w.update("reports to Dana.", "", final=True)
    assert env.field.text == "Send the reports to Dana."
    w.finish()


def test_continues_existing_text():
    env = Env("We ate dinner")
    env.writer.begin()
    env.writer.update("Then we left.", "", final=True)
    assert env.field.text == "We ate dinner then we left."


def test_rules_apply_to_stable_text():
    env = Env()
    env.writer.begin()
    env.writer.update("I drove to mackinaw — it was great period", "", final=True)
    assert env.field.text == "I drove to Mackinac, it was great."


def test_new_line_split_across_updates():
    env = Env()
    env.writer.begin()
    env.writer.update("Thanks new", "line")
    assert env.field.text == "Thanks
"   # "new" held back, then "new line" shown as a newline
    env.writer.update("line see you", "", final=True)
    assert env.field.text == "Thanks\nSee you"


def test_click_into_other_field_freezes_and_continues_there():
    env = Env()
    env.fields["b"] = Field("Other: ")
    w = env.writer
    w.begin()
    w.update("hello", "there")
    env.monitor.user_input = True
    env.focus = "b"
    w.update("there", "friend")
    assert env.fields["a"].text == "Hello there"        # untouched
    assert env.fields["b"].text == "Other: friend"      # old tail not repeated
    w.update("friend.", "", final=True)
    assert env.fields["b"].text == "Other: friend."


def test_user_typing_in_same_field_freezes_without_backspacing():
    env = Env()
    w = env.writer
    w.begin()
    w.update("", "hello there")
    env.field.text += "!!"                               # user typed
    env.monitor.user_input = True
    w.update("hello world", "", final=True)
    assert env.field.text.startswith("Hello there!!")
    assert env.field.backspaces == 0


def test_autocomplete_mismatch_freezes():
    env = Env()
    w = env.writer
    w.begin()
    w.update("", "teh")
    env.field.text = "The"                               # app autocorrected, no physical input
    w.update("the cat", "", final=True)
    assert env.field.backspaces == 0           # never fights the app's correction
    assert env.field.text.startswith("The")


def test_unreadable_field_still_works():
    env = Env(readable=False)
    w = env.writer
    w.begin()
    w.update("", "hello")
    w.update("hello world.", "", final=True)
    assert env.field.text == "Hello world."
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_live_writer.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `shuper_whisper/live_writer.py`**

```python
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

# First words of multi-word spoken commands. Held back while the next word is
# unknown so "new" + "line" can still become a newline.
_HOLD_BACK = frozenset({"new", "question", "exclamation", "full"})
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
```

- [ ] **Step 4: Run the tests and iterate**

Run: `python -m pytest tests/test_live_writer.py -q`
Expected: PASS.
- Where a case fails, step through `update` with the test's inputs and fix the logic.
- Do not weaken the assertions: each one encodes a safety rule from the spec (never backspace user text, never repeat frozen words, never touch the old field).

- [ ] **Step 5: Remove the batch injector**

```bash
git rm shuper_whisper/injector.py tests/test_injector.py
```

(App wiring moves to `LiveWriter` in Task 6.)

- [ ] **Step 6: Commit**

```bash
git add shuper_whisper/live_writer.py tests/test_live_writer.py
git commit -m "feat(writer): live inline typing that only rewrites its own tail and freezes on focus change"
```

---

### Task 5: Caret indicator

**Files:**
- Modify: `shuper_whisper/overlay.py` (rewrite as `CaretIndicator`), `shuper_whisper/tray.py`
- Test: `tests/test_overlay.py` (rewrite)

**Interfaces:**
- Consumes: `caret.caret_rect`, `caret.foreground_rect`, `caret.place_below`
- Produces: `CaretIndicator()` with `.set_window(window)`, `.apply_win32_styles()`, `.show()`, `.hide()`, `.set_state(state)` (`"listening"` or `"finishing"`), `.show_error(message)`, `.update_levels(levels)`, `.reposition(use_uia=False)`, `.is_visible`, `.destroy()`, `BAR_COUNT = 5`, `WIDTH`, `HEIGHT`, `ERROR_WIDTH`, and the module constant `INDICATOR_HTML`.

- [ ] **Step 1: Rewrite `tests/test_overlay.py`**

```python
"""CaretIndicator non-GUI behaviour."""

from shuper_whisper import overlay as ov
from shuper_whisper.overlay import CaretIndicator


class Win:
    def __init__(self):
        self.js = []

    def evaluate_js(self, js):
        self.js.append(js)


def test_initially_hidden():
    assert CaretIndicator().is_visible is False


def test_show_hide_and_states_call_js():
    ind = CaretIndicator()
    w = Win()
    ind.set_window(w)
    ind.show()
    ind.set_state("finishing")
    ind.hide()
    assert w.js[0].startswith("show(") and "setState('finishing')" in w.js and w.js[-1] == "hide()"


def test_error_message_is_escaped():
    ind = CaretIndicator()
    w = Win()
    ind.set_window(w)
    ind.show_error("Can't type into 'admin' windows")
    assert w.js[-1] == 'showError("Can\'t type into \'admin\' windows")'


def test_levels_only_while_visible():
    ind = CaretIndicator()
    w = Win()
    ind.set_window(w)
    ind.update_levels([0.1] * 5)
    assert w.js == []


def test_reposition_uses_caret_then_window(monkeypatch):
    moves = []
    ind = CaretIndicator()
    ind._hwnd = 1
    monkeypatch.setattr(ind, "_move", lambda x, y, w, h: moves.append((x, y)))
    monkeypatch.setattr(ind, "_monitor_for", lambda pt: ((0, 0, 1920, 1040), 1.0))
    monkeypatch.setattr(ov, "caret_rect", lambda use_uia=False: (500, 300, 502, 320))
    ind.reposition()
    monkeypatch.setattr(ov, "caret_rect", lambda use_uia=False: None)
    monkeypatch.setattr(ov, "foreground_rect", lambda: (100, 100, 900, 700))
    ind.reposition()
    assert moves[0] == (494, 326)
    assert moves[1][1] == 700 - ind.HEIGHT - 24
```

- [ ] **Step 2: Rewrite `shuper_whisper/overlay.py`**

```python
"""Small dictation indicator anchored under the text caret.

A pywebview window (transparent, frameless, never focused) holding a pill
with a mic glyph and five level bars. Follows the system light/dark theme.
"""

import ctypes
import ctypes.wintypes
import json
import threading
import time

from .caret import caret_rect, foreground_rect, place_below

INDICATOR_HTML = """\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  :root { --bg: rgba(243,243,243,.94); --fg: #1a1a1a; --muted: #5f5f5f; --accent: #0067c0;
          --border: rgba(0,0,0,.08); --error: #c42b1c; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: rgba(44,44,44,.94); --fg: #ffffff; --muted: #c5c5c5; --accent: #4cc2ff;
            --border: rgba(255,255,255,.08); --error: #ff99a4; } }
  html, body { margin: 0; background: transparent; overflow: hidden; user-select: none;
               font: 12px "Segoe UI Variable Text", "Segoe UI", sans-serif; }
  .pill { position: absolute; left: 4px; top: 4px; height: 28px; padding: 0 12px 0 10px;
          display: flex; align-items: center; gap: 8px; border-radius: 14px; background: var(--bg);
          color: var(--fg); border: 1px solid var(--border);
          box-shadow: 0 2px 8px rgba(0,0,0,.18); opacity: 0; transform: translateY(-2px);
          transition: opacity .12s ease, transform .12s ease; white-space: nowrap; }
  .pill.on { opacity: 1; transform: none; }
  .mic { width: 14px; height: 14px; color: var(--accent); flex: none; }
  .bars { display: flex; align-items: center; gap: 2px; height: 14px; }
  .bars i { display: block; width: 3px; height: 3px; border-radius: 2px; background: var(--accent);
            transition: height .06s linear; }
  .finishing .bars i { animation: pulse 1s ease-in-out infinite; height: 4px; }
  .finishing .bars i:nth-child(2) { animation-delay: .1s } .finishing .bars i:nth-child(3) { animation-delay: .2s }
  .finishing .bars i:nth-child(4) { animation-delay: .3s } .finishing .bars i:nth-child(5) { animation-delay: .4s }
  @keyframes pulse { 50% { opacity: .3 } }
  .msg { display: none; color: var(--error); }
  .error .bars { display: none } .error .msg { display: inline } .error .mic { color: var(--error) }
</style></head><body>
<div class="pill" id="pill">
  <svg class="mic" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a2.5 2.5 0 0 0-2.5 2.5v4a2.5 2.5 0 0 0 5 0v-4A2.5 2.5 0 0 0 8 1Zm-4.5 6a.5.5 0 0 0-1 0 5.5 5.5 0 0 0 5 5.48V14H6a.5.5 0 0 0 0 1h4a.5.5 0 0 0 0-1H8.5v-1.52a5.5 5.5 0 0 0 5-5.48.5.5 0 0 0-1 0 4.5 4.5 0 0 1-9 0Z"/></svg>
  <span class="bars"><i></i><i></i><i></i><i></i><i></i></span>
  <span class="msg" id="msg"></span>
</div>
<script>
  var pill = document.getElementById('pill'), bars = pill.querySelectorAll('.bars i');
  function show() { pill.className = 'pill on'; }
  function hide() { pill.className = 'pill'; }
  function setState(s) { pill.className = 'pill on ' + s; }
  function showError(m) { document.getElementById('msg').textContent = m; pill.className = 'pill on error'; }
  function updateLevels(levels) {
    for (var i = 0; i < bars.length; i++) {
      bars[i].style.height = Math.max(3, Math.min(14, 3 + (levels[i] || 0) / 0.05 * 11)) + 'px';
    }
  }
</script></body></html>
"""


class CaretIndicator:
    WIDTH = 96          # logical px, including the 4 px shadow margin each side
    HEIGHT = 36
    ERROR_WIDTH = 340
    GAP = 6
    BAR_COUNT = 5
    ERROR_SECONDS = 4.0

    def __init__(self):
        self._window = None
        self._hwnd = None
        self._visible = False
        self._width = self.WIDTH

    # -- window plumbing -----------------------------------------------------------

    def set_window(self, window) -> None:
        self._window = window

    def apply_win32_styles(self) -> None:
        """Never activate, never appear in Alt+Tab."""
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "ShuperWhisper Indicator")
        if not hwnd:
            print("WARNING: indicator window not found")
            return
        self._hwnd = hwnd
        GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = -20, 0x08000000, 0x00000080
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)

    def _eval(self, js: str) -> None:
        if self._window:
            try:
                self._window.evaluate_js(js)
            except Exception:
                pass

    @staticmethod
    def _monitor_for(point):
        """(work area, DPI scale) of the monitor containing ``point``."""
        user32 = ctypes.windll.user32

        class _MI(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", ctypes.wintypes.RECT),
                        ("rcWork", ctypes.wintypes.RECT), ("dwFlags", ctypes.c_ulong)]

        hmon = user32.MonitorFromPoint(ctypes.wintypes.POINT(*point), 2)  # NEAREST
        info = _MI(cbSize=ctypes.sizeof(_MI))
        user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        rc = info.rcWork
        scale = 1.0
        try:
            dx, dy = ctypes.c_uint(), ctypes.c_uint()
            ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dx), ctypes.byref(dy))
            scale = dx.value / 96.0
        except Exception:
            pass
        return (rc.left, rc.top, rc.right, rc.bottom), scale

    def _move(self, x, y, w, h) -> None:
        SWP_NOACTIVATE, SWP_NOZORDER = 0x0010, 0x0004
        ctypes.windll.user32.SetWindowPos(self._hwnd, None, x, y, w, h,
                                          SWP_NOACTIVATE | SWP_NOZORDER)

    def reposition(self, use_uia: bool = False) -> None:
        """Sit just under the caret; fall back to the bottom of the window."""
        if not self._hwnd:
            return
        caret = caret_rect(use_uia=use_uia)
        if caret is None:
            window = foreground_rect()
            if window is None:
                return
            work, scale = self._monitor_for(((window[0] + window[2]) // 2, window[3]))
            w, h = int(self._width * scale), int(self.HEIGHT * scale)
            x = (window[0] + window[2] - w) // 2
            self._move(x, window[3] - h - int(24 * scale), w, h)
            return
        work, scale = self._monitor_for((caret[0], caret[3]))
        w, h = int(self._width * scale), int(self.HEIGHT * scale)
        x, y = place_below(caret, work, (w, h), int(self.GAP * scale))
        self._move(x, y, w, h)

    # -- public API ----------------------------------------------------------------

    def show(self) -> None:
        self._visible = True
        self._width = self.WIDTH
        self._eval("show()")
        if self._hwnd:
            self.reposition(use_uia=True)
            ctypes.windll.user32.ShowWindow(self._hwnd, 8)  # SW_SHOWNOACTIVATE

    def set_state(self, state: str) -> None:
        self._eval(f"setState('{state}')")

    def show_error(self, message: str) -> None:
        self._visible = True
        self._width = self.ERROR_WIDTH
        self._eval(f"showError({json.dumps(message)})")
        if self._hwnd:
            self.reposition(use_uia=False)
            ctypes.windll.user32.ShowWindow(self._hwnd, 8)

        def _later():
            time.sleep(self.ERROR_SECONDS)
            self.hide()
        threading.Thread(target=_later, daemon=True).start()

    def hide(self) -> None:
        self._visible = False
        self._eval("hide()")
        if self._hwnd:
            def _later():
                time.sleep(0.15)
                if not self._visible:
                    ctypes.windll.user32.ShowWindow(self._hwnd, 0)
            threading.Thread(target=_later, daemon=True).start()

    def update_levels(self, levels) -> None:
        if not self._visible:
            return
        self._eval("updateLevels([" + ",".join(f"{v:.4f}" for v in levels[:self.BAR_COUNT]) + "])")

    @property
    def is_visible(self) -> bool:
        return self._visible

    def destroy(self) -> None:
        self._visible = False
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
```

Note: `json.dumps` produces a double-quoted JS string literal, so `show_error` needs no hand-escaping.

- [ ] **Step 3: Create the window in `shuper_whisper/tray.py`**

- Replace `from .overlay import OVERLAY_HTML` with `from .overlay import INDICATOR_HTML`.
- In `run()`, replace the overlay `webview.create_window(...)` call with:

```python
        self._overlay_window = webview.create_window(
            'ShuperWhisper Indicator',
            html=INDICATOR_HTML,
            width=CaretIndicator.ERROR_WIDTH,
            height=CaretIndicator.HEIGHT,
            frameless=True,
            hidden=True,
            on_top=True,
            transparent=True,
            focus=False,
        )
```

- Import `CaretIndicator` from `.overlay`.
- In `_on_overlay_loaded`, remove the `apply_colors()` call, leaving only `self.app.overlay.apply_win32_styles()`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_overlay.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shuper_whisper/overlay.py shuper_whisper/tray.py tests/test_overlay.py
git commit -m "feat(indicator): small Fluent pill that follows the text caret"
```

---

### Task 6: Wire live dictation into the app; drop overlay position

**Files:**
- Modify: `shuper_whisper/app.py`, `shuper_whisper/config.py`, `shuper_whisper/bridge.py`, `ui/src/lib/types.ts`, `ui/src/components/GeneralTab.tsx`
- Test: `tests/test_app_lifecycle.py` (rewrite the session tests), `tests/test_config.py`

**Interfaces:**
- Consumes: `StreamingSession`, `Hypothesis`, `LiveWriter`, `CaretIndicator`, `HotkeyManager`, `AudioRecorder.read_new`, `parse_hotkey`, and `_win32_keys.MODIFIER_VK_MAP` / `get_vk`.
- Produces: `ShuperWhisperApp` with `.writer` and `.overlay` (a `CaretIndicator`), plus the session callbacks `_on_hypothesis`, `_auto_stop` and `_on_session_finished`.

- [ ] **Step 1: Config — remove `overlay_position`**

In `tests/test_config.py`:
- delete `test_bad_overlay_position_resets` and `test_valid_positions_kept`, and the `VALID_OVERLAY_POSITIONS` import;
- remove `overlay_position` from `test_defaults` and from `test_round_trip` (both the constructor and the asserted tuple);
- add `"overlay_position"` to the list in `test_removed_fields_are_gone`.

In `config.py`:
- delete `VALID_OVERLAY_POSITIONS`;
- remove the `overlay_position` field and its validation;
- remove it from `_CONFIG_FIELDS`.

In `bridge.py`:
- remove `overlay_position` from `save_config`;
- remove `overlay_positions` (and its import) from `get_config_options`.

In `ui/src/lib/types.ts`, remove `overlay_position` and `overlay_positions`. In `GeneralTab.tsx`, delete `positionLabels`, `positionOptions`, the Overlay Position `FieldRow`, and `MapPin` from the import.

- [ ] **Step 2: Rewrite the session tests in `tests/test_app_lifecycle.py`**

- Keep `FakeRecorder`, `FakeTranscriber` and `FakeHotkeys`.
  - Add `def read_new(self): return np.zeros(0, np.float32)` to `FakeRecorder`.
  - Add `self.device = "cuda"` to `FakeTranscriber.__init__`.
- Replace `FakeOverlay` and the fixture, and add two fakes:

```python
class FakeIndicator:
    BAR_COUNT = 5
    is_visible = False

    def __init__(self):
        self.errors = []

    def show_error(self, m):
        self.errors.append(m)

    def __getattr__(self, name):
        return lambda *a, **k: None


class FakeWriter:
    def __init__(self, **kw):
        self.updates = []
        self.blocked = False

    def begin(self, ignore_vks=()):
        pass

    def update(self, stable, tentative, final=False):
        if self.blocked:
            from shuper_whisper._win32_keys import InjectionBlocked
            raise InjectionBlocked("blocked")
        self.updates.append((stable, tentative, final))

    def finish(self):
        pass


class FakeSession:
    """Emits scripted hypotheses on start; stop() runs on_finished."""
    script = []

    def __init__(self, transcriber, read_audio, on_hypothesis, on_finished, on_auto_stop, **kw):
        self.on_hypothesis, self.on_finished = on_hypothesis, on_finished
        self.on_auto_stop = on_auto_stop
        self.interval = kw.get("interval")

    def start(self):
        for h in FakeSession.script:
            self.on_hypothesis(h)

    def stop(self):
        self.on_finished(None)


@pytest.fixture
def make_app(monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod, "AudioRecorder", FakeRecorder)
    monkeypatch.setattr(app_mod, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(app_mod, "HotkeyManager", FakeHotkeys)
    monkeypatch.setattr(app_mod, "CaretIndicator", FakeIndicator)
    monkeypatch.setattr(app_mod, "LiveWriter", FakeWriter)
    monkeypatch.setattr(app_mod, "StreamingSession", FakeSession)
    monkeypatch.setattr(app_mod.audio_devices, "migrate", lambda v: v)
    monkeypatch.setattr(app_mod, "save_config", lambda c: None)
    FakeSession.script = []

    def _make(**cfg):
        a = app_mod.ShuperWhisperApp(AppConfig(**cfg))
        a.dictionary = app_mod.WordDictionary(path=str(tmp_path / "d.json"))
        states = []
        a.set_state_callback(states.append)
        a.states = states
        return a
    return _make
```

- Keep `test_start_reaches_idle`, `test_model_failure_is_error_not_loading`, `test_mic_failure_at_dictation_is_error_and_resets_hotkey`, `test_recovers_by_picking_a_working_device`, `test_device_change_does_not_reload_model`, `test_second_start_while_finishing_is_ignored` and `test_legacy_device_index_migrated_on_start` exactly as they are.
- Delete `test_full_session_types_clean_text` and `test_silence_types_nothing`, and add:

```python
from shuper_whisper.streaming import Hypothesis


def test_live_session_feeds_writer_and_returns_to_idle(make_app):
    a = make_app()
    a.start()
    FakeSession.script = [Hypothesis("", "hello", False), Hypothesis("hello world.", "", True)]
    a._on_record_start()
    assert a.writer.updates == [("", "hello", False), ("hello world.", "", True)]
    assert a.states[-1] == "recording"
    a._on_record_stop()
    assert a.states[-2:] == ["processing", "idle"]
    assert not a._session_lock.locked()


def test_blocked_typing_stops_session_with_error(make_app):
    a = make_app()
    a.start()
    FakeSession.script = [Hypothesis("hi", "", True)]
    a.writer.blocked = True
    a._on_record_start()          # writer raises -> session stops itself
    assert a.states[-1] == "error" and a.overlay.errors == ["blocked"]
    assert a.hotkey_manager.resets >= 1 and not a._session_lock.locked()


def test_auto_stop_resets_hotkey_and_finishes(make_app):
    a = make_app()
    a.start()
    a._on_record_start()
    a._session.on_auto_stop()
    assert a.hotkey_manager.resets >= 1 and a.states[-1] == "idle"


def test_cpu_uses_slower_interval(make_app):
    a = make_app()
    a.start()
    a.transcriber.device = "cpu"
    a._on_record_start()
    assert a._session.interval == 1.0
```

Run: `python -m pytest tests/test_app_lifecycle.py -q`
Expected: FAIL (`app_mod` has no `CaretIndicator` / `LiveWriter` / `StreamingSession`).

- [ ] **Step 3: Rewrite the session part of `shuper_whisper/app.py`**

Imports:
- Remove `from .injector import TextInjector`, `from .overlay import RecordingOverlay` and `from .text_rules import clean`.
- Add:

```python
from ._win32_keys import MODIFIER_VK_MAP, InjectionBlocked, get_vk
from .hotkey import HotkeyManager, parse_hotkey
from .live_writer import LiveWriter
from .overlay import CaretIndicator
from .streaming import Hypothesis, StreamingSession
```

Delete `SILENCE_RMS_THRESHOLD`.

In `__init__`, replace the `injector` and `overlay` lines with:

```python
        self.writer = LiveWriter(replacements=lambda: self.dictionary.get_replacements())
        self.overlay = CaretIndicator()
        self._session: Optional[StreamingSession] = None
        self._session_error: Optional[str] = None
```

Replace the whole `# -- dictation session --` section (`_on_record_start` through `_stop_level_monitoring`) with:

```python
    def _hotkey_vks(self) -> list[int]:
        modifiers, trigger = parse_hotkey(self.config.hotkey)
        vks = [get_vk(trigger)]
        for mod in modifiers:
            vks.extend(MODIFIER_VK_MAP.get(mod, []))
        return vks

    def _on_record_start(self) -> None:
        if not self._session_lock.acquire(blocking=False):
            self.hotkey_manager.reset()  # previous dictation is still finishing
            return
        try:
            self.recorder.start_recording()
        except Exception as e:
            self._session_lock.release()
            self.hotkey_manager.reset()
            self._fail(f"Microphone: {e}")
            self.overlay.show_error(self.error)
            return
        self._session_error = None
        self.writer.begin(ignore_vks=self._hotkey_vks())
        self._set_state(STATE_RECORDING)
        self.overlay.show()
        self._start_level_monitoring()
        self._session = StreamingSession(
            transcriber=self.transcriber,
            read_audio=self.recorder.read_new,
            on_hypothesis=self._on_hypothesis,
            on_finished=self._on_session_finished,
            on_auto_stop=self._auto_stop,
            prompt=self.dictionary.get_initial_prompt,
            hotwords=self.dictionary.get_hotwords() or None,
            interval=0.4 if self.transcriber.device == "cuda" else 1.0,
        )
        self._session.start()

    def _on_hypothesis(self, hypothesis: Hypothesis) -> None:
        if self._session_error:
            return
        try:
            self.writer.update(hypothesis.stable_delta, hypothesis.tentative,
                               final=hypothesis.final)
        except InjectionBlocked as e:
            self._session_error = str(e)
            if self._session:
                self._session.stop()
            return
        self.overlay.reposition(use_uia=True)

    def _on_record_stop(self) -> None:
        self._stop_level_monitoring()
        self._set_state(STATE_PROCESSING)
        self.overlay.set_state("finishing")
        if self._session:
            self._session.stop()

    def _auto_stop(self) -> None:
        self.hotkey_manager.reset()
        self._on_record_stop()

    def _on_session_finished(self, error: Optional[str]) -> None:
        """Runs on the streaming thread after its final pass."""
        self._stop_level_monitoring()
        self.hotkey_manager.reset()  # session over, however it ended
        try:
            try:
                self.recorder.stop_recording()
            except Exception as e:
                error = error or str(e)
            self.writer.finish()
            error = error or self._session_error or self.recorder.stream_error
            if error:
                self._fail(error)
                self.overlay.show_error(error)
            else:
                self._set_state(STATE_IDLE)
                self.overlay.hide()
        finally:
            self._session = None
            self._session_lock.release()

    def _start_level_monitoring(self) -> None:
        ticks = {"n": 0}

        def _update():
            if self.overlay.is_visible:
                self.overlay.update_levels(self.recorder.get_levels(self.overlay.BAR_COUNT))
                ticks["n"] += 1
                if ticks["n"] % 5 == 0:
                    self.overlay.reposition()
                self._level_timer = threading.Timer(0.033, _update)
                self._level_timer.daemon = True
                self._level_timer.start()
        _update()

    def _stop_level_monitoring(self) -> None:
        if self._level_timer:
            self._level_timer.cancel()
            self._level_timer = None
```

In `reload_config`, delete the `self.overlay.set_position(...)` line. In `__init__`, the overlay is now `CaretIndicator()`, which takes no arguments.

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest tests/ -q`
Expected: PASS. Then confirm nothing still uses the removed names:

```bash
rg -n "overlay_position|RecordingOverlay|TextInjector|OVERLAY_HTML" shuper_whisper tests
```

Expected: no matches.

- [ ] **Step 5: Rebuild the UI**

```bash
cd shuper_whisper/ui && npm run build
```

Expected: builds cleanly.

- [ ] **Step 6: Commit**

```bash
git add -A shuper_whisper tests
git commit -m "feat(app): live dictation — stream hypotheses into the focused field with a caret indicator"
```

---

### Task 7: Manual verification matrix, docs, PR

- [ ] **Step 1: Run from source**

```bash
python main.py --console
```

- [ ] **Step 2: Verify each of these and note the result in the PR body**

| Target | Expect |
|---|---|
| Notepad | Words appear as you speak, the tail fixes itself, the pill sits under the caret. |
| Chrome / Edge textarea (e.g. a GitHub comment box) | Same as Notepad; the pill follows the caret (UIA path). |
| VS Code editor | Text appears, and no autocomplete popup eats the words. If it does, the writer freezes; note it. |
| Windows Terminal | Text appears at the prompt. |
| Mid-sentence click into a second Notepad | The first window keeps its text untouched; dictation continues in the second, with no repeated words. |
| Typing a key mid-dictation | No backspacing over what you typed. |
| "new line" / "period" spoken | A line break / a full stop, even when split across updates. |
| 30 s of silence | Dictation stops by itself; the next hotkey press starts fresh. |
| Admin window (e.g. elevated PowerShell) | The pill shows "Windows blocked typing…", and the app stays usable. |
| Voicemeeter Out B1 | Works live. |
| Clipboard | Unchanged after all of the above. |
| `SHUPER_WHISPER_DEVICE=cpu` | Still live, with slower 1 s updates. |

- [ ] **Step 3: README**

Update "How it works": text appears live as you speak, the last few words may adjust themselves, and clicking another field continues dictation there.

```bash
git add README.md && git commit -m "docs: live dictation behaviour"
```

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/stage2-live-dictation
source D:/dev/scripts/profile.sh && infisical-load-env && curl -sf -X POST \
  -H "Authorization: token $GITEA_TOKEN" -H "Content-Type: application/json" \
  "$GITEA_URL/api/v1/repos/shuper/shuperwhisper/pulls" -d @- <<'EOF'
{"base":"main","head":"feat/stage2-live-dictation","title":"Stage 2: live inline dictation",
 "body":"Implements stage 2 of docs/superpowers/specs/2026-10-04-live-dictation-design.md.\n\n- StreamingSession: LocalAgreement-2 over ~400 ms re-decodes, VAD-bounded utterances, 30 s auto-stop\n- LiveWriter: types into the focused field and rewrites only its own tail; freezes on focus change, physical input or autocomplete mismatch\n- Caret-anchored indicator pill (light/dark)\n- Removed batch injector and overlay position setting\n\nManual verification: see table below.\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"}
EOF
```

Then edit the PR body to include the filled-in verification table from Step 2. Never merge it.

- [ ] **Step 5: Whole-branch review**

Review the whole branch once, on the most capable model, against the spec's Stage 2 section and this plan (`git diff main...feat/stage2-live-dictation`). Fix the findings on the same branch.
