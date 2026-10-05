"""Live decoding: re-transcribe the current utterance every few hundred ms.

LocalAgreement-2: a word is *stable* once two consecutive hypotheses agree on
it (and everything before it). Stable words are committed; the rest of the
newest hypothesis is a *tentative* tail the writer may still rewrite.

Utterances are bounded by Silero VAD: after END_SILENCE of quiet the words
are committed and the buffer restarts, so each decode stays short. Whisper
treats every utterance as a finished sentence, though, so a mid-sentence
pause would leave "testing things out. Right now." -- therefore the sentence
punctuation at an utterance's end stays revisable, and the audio of its last
few words is carried into the next utterance. When speech continues, the
silence between them is shortened (Whisper reads a long pause as a sentence
end regardless of grammar) and Whisper re-reads the boundary with the new
words as context; if the sentence didn't end ("out right now"), the full
stop is taken back.
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


_SENTENCE_END = ".?!…"


def _sentence_end(word: str) -> str:
    """Trailing sentence punctuation of ``word`` ("" if none)."""
    return word[len(word.rstrip(_SENTENCE_END)):]


def _trailing_mark(word: str) -> str:
    """Any trailing punctuation: what a re-read may put in place of a held
    full stop ("Alright." -> "Alright,")."""
    return word[len(word.rstrip(_SENTENCE_END + ",;:")):]


class LocalAgreement:
    # Share of the committed characters a re-worded hypothesis must still
    # contain before we trust it to tell us where the new words start.
    MIN_OVERLAP = 0.6

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._prev: list[str] = []
        self._stable_words: list[str] = []
        # The last committed word went out without its sentence punctuation:
        # Whisper ends sentences at pauses ("out. Right") and changes its mind
        # when speech continues ("out right now"), so the "." stays tentative
        # until the next word is committed.
        self._held = False
        self._held_mark = ""

    def _pending_end(self, rebased: list[str]) -> list[str]:
        """The held punctuation as the latest hypothesis has it, as a token."""
        n = len(self._stable_words)
        if not self._held or n == 0 or n > len(rebased):
            return []
        end = _trailing_mark(rebased[n - 1])
        return [end] if end else []

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
            # Same words: take the new wording, so a changed mind about a held
            # sentence mark ("out." -> "out") shows up.
            return list(words)
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
                # Committed words keep their wording, but the boundary word's
                # punctuation follows the new hypothesis.
                last = self._stable_words[-1]
                last = last[:len(last) - len(_trailing_mark(last))] + _trailing_mark(words[i])
                return self._stable_words[:-1] + [last] + list(words[i + 1:])
        return list(self._stable_words)

    @property
    def held(self) -> bool:
        return self._held

    @property
    def stable_words(self) -> list[str]:
        return list(self._stable_words)

    def seed(self, words: list[str]) -> None:
        """Start a new utterance whose audio begins with these already
        committed words (carried over); any held punctuation stays held."""
        self._stable_words = list(words)
        self._prev = list(words)
        if not words:
            self._held = False

    def commit_all(self, words: list[str]) -> tuple[list[str], list[str]]:
        """End of an utterance, mid-dictation: commit every word, but keep
        the last word's sentence punctuation tentative (see _held).
        Returns (newly committed, tentative)."""
        rebased = (self._rebase(words) if words else None) or self._prev
        newly = self._pending_end(rebased) + rebased[len(self._stable_words):]
        self._stable_words = list(rebased)
        self._prev = list(rebased)
        if not newly:
            return [], self._pending_end(rebased)
        end = _sentence_end(newly[-1])
        if end:
            newly[-1] = newly[-1][:-len(end)]
            if not newly[-1]:
                newly.pop()
        self._held = bool(end)
        self._held_mark = end
        return newly, [end] if end else []

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
        # Never commit the newest word: it carries Whisper's guess at how the
        # buffer ends ("out." during a pause) and must stay revisable.
        agree = min(agree, len(rebased) - 1)
        self._prev = rebased
        newly: list[str] = []
        if agree > n:
            newly = self._pending_end(rebased) + rebased[n:agree]
            end = _sentence_end(newly[-1])
            if end:
                newly[-1] = newly[-1][:-len(end)]
            self._held = bool(end)
            self._stable_words = rebased[:agree]
        return newly, self._pending_end(rebased) + rebased[len(self._stable_words):]

    def flush(self, words: Optional[list[str]] = None) -> list[str]:
        """End of utterance: everything not yet stable becomes stable.

        An empty or contradicting final pass carries no information; the last
        good hypothesis is used instead.
        """
        rebased = self._rebase(words) if words else None
        if rebased is None:
            rebased = self._prev
        n = len(self._stable_words)
        new_words = rebased[n:]
        pending = self._pending_end(rebased)
        if not pending and not new_words:
            if self._held:
                # Nothing was said after the held mark; a re-read of just that
                # fragment often drops it, but the sentence did end there.
                pending = [self._held_mark]
            elif words and n:
                # An utterance can close without a full stop that a careful
                # re-read of its last words finds.
                end = _sentence_end(rebased[n - 1])
                pending = [end] if end else []
        rest = pending + new_words
        self.reset()
        return rest


def silero_speech_spans(audio: np.ndarray) -> list[tuple[int, int]]:
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    options = VadOptions(min_silence_duration_ms=300, speech_pad_ms=100)
    return [(s["start"], s["end"]) for s in get_speech_timestamps(audio, options)]


class StreamingSession:
    END_SILENCE = 0.8
    MAX_UTTERANCE = 25.0
    AUTO_STOP = 30.0
    PROMPT_CHARS = 200
    CAP_KEEP = 1.0       # at the cap, commit only words ending a second before the end
    CARRY_SECONDS = 1.5  # audio of the last committed words carried into the next utterance
    CARRY_WORDS = 4
    JOIN_GAP = 0.25      # silence left between carried words and new speech
    # VAD pads speech and word timestamps run early: speech has to end this
    # far past the carried words to count as new.
    NEW_SPEECH_MARGIN = 0.4
    # How often to look for the end of an utterance. VAD is cheap; decoding
    # isn't, so it runs every ``interval``. Checking only at decodes missed
    # pauses that ended between two of them.
    POLL = 0.1

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
        self._committed: list[str] = []  # every committed word, for the prompt
        self._carried = 0      # how many of those are still in the buffer's audio
        self._carry_end = 0    # buffer sample where the carried words end
        self._gap_closed = True  # the pause after the carried words was shortened
        self._last_tentative = ""
        self._last_speech = clock()
        self._next_decode = 0.0
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
        # Only words whose audio has left the buffer: Whisper skips audio that
        # the prompt already covers, which shifted every later word.
        done = self._committed[:len(self._committed) - self._agreement.stable_count]
        parts = [self._prompt_fn() or "", " ".join(done)[-self.PROMPT_CHARS:]]
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
        self._committed += [w for w in newly if _norm(w)]
        self._on_hypothesis(Hypothesis(stable_text, tentative_text, final))

    def _append_audio(self) -> list:
        chunk = self._read_audio()
        if len(chunk):
            self._buffer = np.concatenate([self._buffer, chunk])
        return self._speech_spans(self._buffer) if len(self._buffer) else []

    def _close_utterance(self, timed: list, keep: int) -> None:
        """Commit the first ``keep`` words (their last sentence mark stays
        revisable), then restart the buffer at the audio of the last few of
        them so the next utterance re-reads that boundary."""
        words = [w for w, _end in timed]
        newly, tentative = self._agreement.commit_all(words[:keep])
        self._emit(newly, tentative)
        if keep == 0:
            return
        end_t = timed[keep - 1][1]
        k = 1
        while k < min(self.CARRY_WORDS, keep):
            earlier = timed[keep - k - 2][1] if keep - k - 2 >= 0 else 0.0
            if end_t - earlier > self.CARRY_SECONDS:
                break
            k += 1
        start_t = timed[keep - k - 1][1] if keep - k - 1 >= 0 else 0.0
        self._agreement.seed(self._agreement.stable_words[-k:])
        start = max(0, int(start_t * SAMPLE_RATE))
        self._buffer = self._buffer[start:]
        self._carry_end = max(0, int(end_t * SAMPLE_RATE) - start)
        self._gap_closed = False

    @property
    def _margin(self) -> int:
        return int(self.NEW_SPEECH_MARGIN * SAMPLE_RATE) if self._carry_end else 0

    def _close_gap(self, spans: list) -> list:
        """Once speech resumes after carried words, cut the pause between
        them down to JOIN_GAP, so Whisper judges the boundary on the words."""
        if self._gap_closed or not self._carry_end:
            return spans
        resumed = [s for s in spans if s[0] > self._carry_end + self._margin]
        if not resumed:
            return spans
        self._gap_closed = True
        keep = int(self.JOIN_GAP * SAMPLE_RATE)
        cut_from, cut_to = self._carry_end + keep // 2, resumed[0][0] - keep // 2
        if cut_to - cut_from > SAMPLE_RATE // 10:
            self._buffer = np.concatenate([self._buffer[:cut_from], self._buffer[cut_to:]])
            spans = self._speech_spans(self._buffer)
        return spans

    def _cut_at_cap(self) -> None:
        """A long stretch without a pause: close the utterance at a word
        boundary about a second from the end, so no word is split."""
        timed = self._decode(timestamps=True)
        limit = len(self._buffer) / SAMPLE_RATE - self.CAP_KEEP
        keep = sum(1 for _w, end in timed if end <= limit)
        keep = min(max(keep, self._agreement.stable_count), len(timed))
        self._close_utterance(timed, keep)

    def _tick(self) -> None:
        spans = self._append_audio()
        if self._stop.is_set():
            return  # the final pass in _run() decodes what's left
        now = self._clock()
        if not spans and self._carry_end and not self._gap_closed:
            # VAD often misses a lone carried word (its audio starts abruptly),
            # but we know it's there: keep waiting for new speech.
            spans = [(0, self._carry_end)]
        if not spans:
            if self._agreement.stable_count or self._last_tentative:
                # Speech vanished (VAD dropout or it was noise): close the
                # utterance so stale agreement can't swallow the next one, and
                # drop its audio, now committed, so it isn't decoded again.
                self._emit(self._agreement.flush(), [], final=True)
                self._carry_end = 0
                self._buffer = self._buffer[-int(0.3 * SAMPLE_RATE):]
            if len(self._buffer) > 2 * SAMPLE_RATE:
                self._buffer = self._buffer[-SAMPLE_RATE // 2:]
            if not self._auto_stopped and now - self._last_speech >= self.AUTO_STOP:
                self._auto_stopped = True
                self._on_auto_stop()
            return
        spans = self._close_gap(spans)
        if not spans:
            return
        speech_end = spans[-1][1]
        silence_after = (len(self._buffer) - speech_end) / SAMPLE_RATE
        if speech_end <= self._carry_end + self._margin:
            # Only the carried-over words so far: wait for new speech, and
            # don't let the silence after them pile up. (They aren't new
            # speech, so the auto-stop clock keeps running.)
            limit = speech_end + SAMPLE_RATE // 2
            if len(self._buffer) > limit + SAMPLE_RATE:
                # keep the newest 0.3 s: speech may be starting that VAD hasn't flagged yet
                self._buffer = np.concatenate([self._buffer[:limit],
                                               self._buffer[-int(0.3 * SAMPLE_RATE):]])
            if not self._auto_stopped and now - self._last_speech >= self.AUTO_STOP:
                self._auto_stopped = True
                self._on_auto_stop()
            return
        self._last_speech = now - silence_after
        if len(self._buffer) >= self.MAX_UTTERANCE * SAMPLE_RATE and silence_after < self.END_SILENCE:
            self._cut_at_cap()
            return
        if silence_after >= self.END_SILENCE:
            timed = self._decode(timestamps=True)
            self._close_utterance(timed, len(timed))
            return
        if now < self._next_decode:
            return
        words = self._decode()
        self._next_decode = self._clock() + self._interval
        newly, tentative = self._agreement.update(words)
        self._emit(newly, tentative)

    def _run(self) -> None:
        error: Optional[str] = None
        try:
            while not self._stop.wait(min(self.POLL, self._interval)):
                self._tick()
            spans = self._close_gap(self._append_audio())
            if spans and spans[-1][1] > self._carry_end + self._margin:
                self._emit(self._agreement.flush(self._decode(beam_size=5)), [], final=True)
            elif self._carry_end and not self._agreement.held:
                # Nothing new, and the last utterance closed without a
                # sentence mark: re-read its carried words carefully.
                self._emit(self._agreement.flush(self._decode(beam_size=5)), [], final=True)
            else:
                # nothing new since the last utterance closed: its held
                # sentence mark stands
                self._emit(self._agreement.flush(), [], final=True)
        except Exception as e:
            error = str(e)
        finally:
            self._on_finished(error)
