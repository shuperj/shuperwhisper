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
        self._stable_norm: list[str] = []

    def _aligned(self, words: list[str]) -> bool:
        """Does ``words`` still start with what we've already committed?"""
        n = self._stable
        return len(words) >= n and [_norm(w) for w in words[:n]] == self._stable_norm

    def update(self, words: list[str]) -> tuple[list[str], list[str]]:
        """Returns (newly stable words, tentative words).

        A hypothesis that contradicts committed words (Whisper sometimes drops
        or rewrites the start of a short buffer) is ignored, not trusted.
        """
        if not self._aligned(words):
            return [], self._prev[self._stable:]
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
            self._stable_norm = [_norm(w) for w in words[:agree]]
        return newly, words[self._stable:]

    def flush(self, words: Optional[list[str]] = None) -> list[str]:
        """End of utterance: everything not yet stable becomes stable."""
        if words is None or not self._aligned(words):
            words = self._prev
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
