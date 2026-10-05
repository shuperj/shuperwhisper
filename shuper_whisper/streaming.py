"""Live decoding: re-transcribe the current utterance every few hundred ms.

LocalAgreement-2: a word is *stable* once two consecutive hypotheses agree on
it (and everything before it). Stable words are committed; the rest of the
newest hypothesis is a *tentative* tail the writer may still rewrite.

Utterances are bounded by Silero VAD: after END_SILENCE of quiet, everything
is committed and the buffer restarts, so each decode stays short.
"""

import difflib
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
    # Share of the committed characters a re-worded hypothesis must still
    # contain before we trust it to tell us where the new words start.
    MIN_OVERLAP = 0.6

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._prev: list[str] = []
        self._stable_words: list[str] = []

    @property
    def stable_count(self) -> int:
        return len(self._stable_words)

    def _rebase(self, words: list[str]) -> Optional[list[str]]:
        """Re-express ``words`` as <committed words> + <what follows them>.

        Whisper re-decodes the whole utterance each pass and may re-word what
        we already committed ("all right" -> "alright", "10" -> "ten"). Match
        the committed text against the hypothesis character by character to
        find where the new words start. None if the hypothesis doesn't
        contain the committed text at all (then it's ignored).
        """
        n = len(self._stable_words)
        if n == 0:
            return list(words)
        normed = [_norm(w) for w in words]
        committed = [_norm(w) for w in self._stable_words]
        if normed[:n] == committed:
            return self._stable_words + list(words[n:])
        a, b = "".join(committed), "".join(normed)
        if not a:
            return self._stable_words + list(words[n:])
        matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
        blocks = [m for m in matcher.get_matching_blocks() if m.size]
        if not blocks or sum(m.size for m in blocks) < self.MIN_OVERLAP * len(a):
            return None
        last = blocks[-1]
        end_b = last.b + last.size + (len(a) - (last.a + last.size))
        total = 0
        for i, w in enumerate(normed):
            total += len(w)
            if total >= end_b:
                return self._stable_words + list(words[i + 1:])
        return list(self._stable_words)

    def update(self, words: list[str]) -> tuple[list[str], list[str]]:
        """Returns (newly stable words, tentative words).

        A hypothesis that doesn't contain the committed words (Whisper
        sometimes drops the start of a short buffer) is ignored, not trusted.
        """
        n = len(self._stable_words)
        rebased = self._rebase(words) if words else None
        if rebased is None:
            return [], self._prev[n:]
        agree = 0
        for a, b in zip(self._prev, rebased):
            if _norm(a) != _norm(b):
                break
            agree += 1
        self._prev = rebased
        newly: list[str] = []
        if agree > n:
            newly = rebased[n:agree]
            self._stable_words = rebased[:agree]
        return newly, rebased[len(self._stable_words):]

    def flush(self, words: Optional[list[str]] = None) -> list[str]:
        """End of utterance: everything not yet stable becomes stable.

        An empty or contradicting final pass carries no information; the last
        good hypothesis is used instead.
        """
        rebased = self._rebase(words) if words else None
        if rebased is None:
            rebased = self._prev
        rest = rebased[len(self._stable_words):]
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
    CAP_KEEP = 1.0  # at the cap, the last second is carried into the next utterance

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
        self._committed = ""   # text of finished utterances (prompt context)
        self._utterance = ""   # stable text of the utterance in progress
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
        # Only *finished* utterances: words of the current one are still in
        # the buffer, and Whisper skips audio that the prompt already covers.
        parts = [self._prompt_fn() or "", self._committed.strip()[-self.PROMPT_CHARS:]]
        return " ".join(p for p in parts if p) or None

    def _decode(self, beam_size: int = 1, timestamps: bool = False):
        started = self._clock()
        result = self._transcriber.transcribe_words(
            self._buffer, initial_prompt=self._prompt(), hotwords=self._hotwords,
            beam_size=beam_size, timestamps=timestamps)
        self._interval = max(self._base_interval, (self._clock() - started) * 1.2)
        return result

    def _emit(self, newly: list[str], tentative: list[str], final: bool = False) -> None:
        stable_text, tentative_text = " ".join(newly), " ".join(tentative)
        if not final and not stable_text and tentative_text == self._last_tentative:
            return
        self._last_tentative = tentative_text
        if stable_text:
            self._utterance += " " + stable_text
        if final:
            self._committed += self._utterance
            self._utterance = ""
        self._on_hypothesis(Hypothesis(stable_text, tentative_text, final))

    def _append_audio(self) -> list:
        chunk = self._read_audio()
        if len(chunk):
            self._buffer = np.concatenate([self._buffer, chunk])
        return self._speech_spans(self._buffer) if len(self._buffer) else []

    def _cut_at_cap(self) -> None:
        """A long stretch without a pause: commit up to a word boundary about a
        second from the end and carry the rest of the audio over, so no word
        is split between utterances."""
        timed = self._decode(timestamps=True)
        words = [w for w, _end in timed]
        limit = len(self._buffer) / SAMPLE_RATE - self.CAP_KEEP
        keep = sum(1 for _w, end in timed if end <= limit)
        keep = min(max(keep, self._agreement.stable_count), len(timed))
        self._emit(self._agreement.flush(words[:keep]), [], final=True)
        cut = timed[keep - 1][1] if keep else limit
        self._buffer = self._buffer[max(0, int(cut * SAMPLE_RATE)):]

    def _tick(self) -> None:
        spans = self._append_audio()
        if self._stop.is_set():
            return  # the final pass in _run() decodes what's left
        now = self._clock()
        if not spans:
            if self._agreement.stable_count or self._last_tentative:
                # Speech vanished (VAD dropout or it was noise): close the
                # utterance so stale agreement can't swallow the next one.
                self._emit(self._agreement.flush(), [], final=True)
            if len(self._buffer) > 2 * SAMPLE_RATE:
                self._buffer = self._buffer[-SAMPLE_RATE // 2:]
            if not self._auto_stopped and now - self._last_speech >= self.AUTO_STOP:
                self._auto_stopped = True
                self._on_auto_stop()
            return
        speech_end = spans[-1][1]
        silence_after = (len(self._buffer) - speech_end) / SAMPLE_RATE
        self._last_speech = now - silence_after
        if len(self._buffer) >= self.MAX_UTTERANCE * SAMPLE_RATE and silence_after < self.END_SILENCE:
            self._cut_at_cap()
            return
        words = self._decode()
        if silence_after >= self.END_SILENCE:
            self._emit(self._agreement.flush(words), [], final=True)
            self._buffer = self._buffer[speech_end:]
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
