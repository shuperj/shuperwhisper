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
        assert la.update(["a", "x"]) == ([], ["d"])   # contradicting hypothesis ignored

    def test_flush_returns_rest(self):
        la = LocalAgreement()
        la.update(["a", "b"])
        la.update(["a", "b", "c"])
        assert la.flush(["a", "b", "c", "d"]) == ["c", "d"]
        assert la.update(["new"]) == ([], ["new"])

    def test_hypothesis_missing_committed_words_is_ignored(self):
        la = LocalAgreement()
        la.update(["hey", "dana", "I"])
        la.update(["hey", "dana", "I", "wanted"])
        assert la.update(["follow", "up"]) == ([], ["wanted"])
        assert la.flush(["follow", "up"]) == ["wanted"]

    def test_flush_without_words_uses_last_hypothesis(self):
        la = LocalAgreement()
        la.update(["a", "b"])
        assert la.flush() == ["a", "b"]


class TestRewording:
    def test_reworded_commit_keeps_following_words(self):
        la = LocalAgreement()
        la.update("we will be all right".split())
        la.update("we will be all right so".split())          # stable: all six
        newly, tentative = la.update("we will be alright so let's go to the shop".split())
        assert tentative == ["let's", "go", "to", "the", "shop"]
        assert la.flush("we will be alright so let's go to the shop now".split()) == \
            ["let's", "go", "to", "the", "shop", "now"]

    def test_final_pass_with_different_wording(self):
        la = LocalAgreement()
        la.update("I'm gonna send it".split())
        la.update("I'm gonna send it to".split())
        assert la.flush("I'm going to send it to Dana.".split()) == ["to", "Dana."]

    def test_empty_final_pass_keeps_last_hypothesis(self):
        la = LocalAgreement()
        la.update(["hello"])
        assert la.flush([]) == ["hello"]


class FakeTranscriber:
    def __init__(self, decodes):
        self.decodes = list(decodes)
        self.calls = []

    def transcribe_words(self, audio, initial_prompt=None, hotwords=None, beam_size=1,
                         timestamps=False):
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


def test_vad_dropout_closes_the_utterance():
    ticks = [(0.4, [(0, 6400)]), (0.4, [(0, 12800)]), (2.0, []), (0.4, [(0, 6400)])]
    decodes = [["how", "are"], ["how", "are", "you"], ["doing", "today"]]
    _s, hyps, _f, _a = run(ticks, decodes)
    assert Hypothesis("", "", True) not in hyps[:2]
    finals = [h for h in hyps if h.final]
    assert finals[0] == Hypothesis("you", "", True)       # closed on the dropout
    assert any("doing" in h.tentative for h in hyps)      # next utterance not swallowed


def test_cap_cuts_at_a_word_boundary():
    class Timed(FakeTranscriber):
        def transcribe_words(self, audio, initial_prompt=None, hotwords=None, beam_size=1,
                             timestamps=False):
            self.calls.append((len(audio), initial_prompt, beam_size))
            if timestamps:
                return [("one", 10.0), ("two", 23.0), ("thr-", 25.4)]
            return ["one", "two"]
    clock = Clock()
    hyps = []
    s = StreamingSession(transcriber=Timed([]), read_audio=lambda: np.zeros(0, np.float32),
                         on_hypothesis=hyps.append, on_finished=lambda e: None,
                         on_auto_stop=lambda: None, interval=0.0,
                         speech_spans=lambda a: [(0, len(a))], clock=clock)
    s._buffer = np.full(int(25.5 * SR), 0.1, np.float32)
    s._tick()
    assert hyps == [Hypothesis("one two", "", True)]
    assert abs(len(s._buffer) / SR - 2.5) < 0.01          # audio after "two" carried over
