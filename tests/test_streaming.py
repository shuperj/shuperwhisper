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

    def test_last_word_never_committed(self):
        la = LocalAgreement()
        la.update(["testing", "things", "out."])
        assert la.update(["testing", "things", "out."]) == (["testing", "things"], ["out."])
        assert la.update(["testing", "things", "out", "right", "now."]) == (["out"], ["right", "now."])

    def test_full_stop_at_a_pause_stays_revisable(self):
        la2 = LocalAgreement()
        la2.update("testing things out. Right".split())
        assert la2.update("testing things out. Right".split()) == (["testing", "things", "out"], [".", "Right"])
        # speech continued: Whisper drops the full stop, so it never gets typed
        assert la2.update("testing things out right now".split()) == (["right"], ["now"])

    def test_kept_full_stop_is_committed_with_the_next_word(self):
        la = LocalAgreement()
        la.update("done. Next".split())
        la.update("done. Next".split())
        assert la.update("done. Next one".split()) == ([".", "Next"], ["one"])
        assert la.flush("done. Next one.".split()) == ["one."]

    def test_punctuation_and_case_ignored_for_agreement(self):
        la = LocalAgreement()
        la.update(["Send", "the"])
        newly, tentative = la.update(["send,", "the", "report"])
        assert newly == ["send,", "the"] and tentative == ["report"]

    def test_stable_never_shrinks(self):
        la = LocalAgreement()
        la.update(["a", "b", "c", "d"])
        la.update(["a", "b", "c", "d", "e"])
        assert la.update(["a", "x"]) == ([], ["e"])   # contradicting hypothesis ignored

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
        words = self.decodes.pop(0) if self.decodes else []
        if timestamps:  # a word every 0.25 s
            return [(w, (i + 1) * 0.25) for i, w in enumerate(words)]
        return words


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


def test_words_stream_then_utterance_ends_with_a_revisable_full_stop():
    ticks = [
        (0.4, [(0, 6400)]),
        (0.4, [(0, 12800)]),
        (1.2, [(0, 12800)]),          # 1.2 s silence after speech -> utterance ends
    ]
    decodes = [["send", "the"], ["send", "the", "report"], ["Send", "the", "report."]]
    _s, hyps, finished, _ = run(ticks, decodes)
    assert hyps[0] == Hypothesis("", "send the", False)
    assert hyps[1] == Hypothesis("send the", "report", False)
    assert hyps[2] == Hypothesis("report", ".", False)    # the "." can still be taken back
    assert hyps[3] == Hypothesis(".", "", True)           # dictation ended: it stays
    assert finished == [None]


def test_sentence_break_taken_back_when_speech_continues():
    ticks = [
        (0.4, [(0, 6400)]),
        (0.4, [(0, 12800)]),
        (1.2, [(0, 12800)]),                       # pause: utterance ends at "out."
        (0.4, [(0, 12800), (32000, 38400)]),       # speech continues
    ]
    decodes = [["testing", "things"], ["testing", "things", "out."],
               ["testing", "things", "out."],                        # close (timestamps)
               ["testing", "things", "out", "right", "now"]]        # boundary re-read: no "."
    _s, hyps, _f, _a = run(ticks, decodes)
    assert hyps[2] == Hypothesis("out", ".", False)
    assert hyps[3] == Hypothesis("", "right now", False)            # the "." is withdrawn
    assert hyps[-1] == Hypothesis("right now", "", True)
    assert not any("." in h.stable_delta for h in hyps)


def test_sentence_break_kept_when_whisper_still_wants_it():
    ticks = [(0.4, [(0, 6400)]), (0.4, [(0, 12800)]), (1.2, [(0, 12800)]),
             (0.4, [(0, 12800), (32000, 38400)]), (0.4, [(0, 12800), (32000, 44800)])]
    decodes = [["all", "done"], ["all", "done."], ["all", "done."],
               ["all", "done.", "Next"], ["all", "done.", "Next", "thing"]]
    _s, hyps, _f, _a = run(ticks, decodes)
    assert Hypothesis(". Next", "thing", False) in hyps


def test_prompt_leaves_out_words_still_in_the_audio():
    s = StreamingSession(transcriber=FakeTranscriber([]), read_audio=lambda: np.zeros(0, np.float32),
                         on_hypothesis=lambda h: None, on_finished=lambda e: None,
                         on_auto_stop=lambda: None, prompt=lambda: "Vocabulary: Dana.")
    s._committed = ["one", "two", "three", "four"]
    s._agreement.seed(["three", "four"])
    assert s._prompt() == "Vocabulary: Dana. one two"


def test_no_speech_emits_nothing_and_final_is_quiet():
    _s, hyps, finished, _ = run([(0.4, []), (0.4, [])], [])
    assert hyps == [Hypothesis("", "", True)] and finished == [None]


def test_stop_mid_utterance_does_final_beam_pass():
    ticks = [(0.4, [(0, 6400)])]
    decodes = [["hello"], ["Hello", "world."]]
    s, hyps, finished, _ = run(ticks, decodes)
    assert hyps[-1] == Hypothesis("Hello world.", "", True)
    assert s._transcriber.calls[-1][2] == 5


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
    assert hyps == [Hypothesis("one two", "", False)]
    assert abs(len(s._buffer) / SR - 15.5) < 0.01         # "two" onwards carried over
    assert s._agreement.stable_words == ["two"]


def test_held_full_stop_survives_a_final_reread_that_drops_it():
    la = LocalAgreement()
    la.commit_all("if anything changes.".split())
    la.seed(["anything", "changes."])
    assert la.flush(["anything", "changes"]) == ["."]


def test_carried_word_missed_by_vad_is_not_typed_again():
    ticks = [
        (0.4, [(0, 6400)]),
        (1.2, [(0, 6400)]),                    # pause: utterance ends at "Alright."
        (0.4, []),                             # VAD misses the lone carried word
        (0.4, [(16000, 22400)]),               # new speech
        (0.4, [(16000, 28800)]),
    ]
    decodes = [["Alright."], ["Alright."],
               ["All", "right,", "so", "I'm"], ["All", "right,", "so", "I'm", "testing"]]
    _s, hyps, _f, _a = run(ticks, decodes)
    typed = "".join(h.stable_delta + " " for h in hyps)
    assert "All right" not in typed and "All right" not in " ".join(h.tentative for h in hyps)
    assert not any(h.final for h in hyps[:-1])            # the "." stayed revisable
    assert hyps[-1].final


def test_full_stop_can_become_a_comma():
    la = LocalAgreement()
    la.commit_all(["Alright."])
    la.seed(["Alright."])
    newly, tentative = la.update(["All", "right,", "so", "I'm"])
    assert tentative[:2] == [",", "so"]


def test_vad_dropout_drops_the_committed_audio():
    ticks = [(0.4, [(0, 6400)]), (0.4, [(0, 12800)]), (0.4, [])]
    decodes = [["how", "are"], ["how", "are", "you"]]
    s, _h, _f, _a = run(ticks, decodes)
    assert len(s._buffer) <= int(0.3 * SR)


def test_auto_stop_while_only_carried_words_wait():
    ticks = [(0.4, [(0, 6400)]), (1.2, [(0, 6400)])] + [(0.4, [(0, 6400)])] * 80
    decodes = [["done."], ["done."]]
    _s, _h, _f, auto = run(ticks, decodes)
    assert auto == [True]



def test_polls_for_silence_between_decodes():
    clock = Clock()
    s = StreamingSession(transcriber=FakeTranscriber([["one"], ["one"]]),
                         read_audio=lambda: np.full(int(0.1 * SR), 0.1, np.float32),
                         on_hypothesis=lambda h: None, on_finished=lambda e: None,
                         on_auto_stop=lambda: None, interval=0.4,
                         speech_spans=lambda a: [(0, len(a))], clock=clock)
    s._tick()
    assert len(s._transcriber.calls) == 1
    clock.t += 0.1
    s._tick()                                    # too soon to decode again
    assert len(s._transcriber.calls) == 1
    clock.t += 0.4
    s._tick()
    assert len(s._transcriber.calls) == 2


def test_final_reread_can_add_a_missing_full_stop():
    la = LocalAgreement()
    la.commit_all("it seems to work".split())
    la.seed(["to", "work"])
    assert la.flush(["to", "work."]) == ["."]
    la.commit_all("it seems to work".split())
    la.seed(["to", "work"])
    assert la.flush(["to", "work"]) == []


def test_noise_without_words_does_not_pile_up_in_the_buffer():
    # A click that VAD takes for speech, then silence: Whisper finds no words.
    # Kept, that audio grew forever and Whisper invented speech to fill it.
    clock = Clock()
    s = StreamingSession(transcriber=FakeTranscriber([]),
                         read_audio=lambda: np.full(int(0.4 * SR), 0.01, np.float32),
                         on_hypothesis=lambda h: None, on_finished=lambda e: None,
                         on_auto_stop=lambda: None, interval=0.0,
                         speech_spans=lambda a: [(0, 1600)] if len(a) > 1600 else [], clock=clock)
    for _ in range(50):                                   # 20 s
        clock.t += 0.4
        s._tick()
    assert len(s._buffer) < 3 * SR


def test_new_speech_survives_carried_words_that_were_misheard():
    ticks = [
        (0.4, [(0, 6400)]),
        (1.2, [(0, 6400)]),                       # pause: closes "send me a message?"
        (0.4, [(0, 6400), (32000, 38400)]),       # new speech
        (0.4, [(0, 6400), (32000, 44800)]),
        (0.4, [(0, 6400), (32000, 51200)]),
    ]
    decodes = [["send", "me", "a", "message?"], ["send", "me", "a", "message?"],
               ["Hey,", "I", "am"],                          # no carried words: a miss
               ["Hey,", "I", "am", "just"],                  # second miss: drop the carry
               ["Hey,", "I", "am", "just"],                  # re-decode of the new speech alone
               ["Hey,", "I", "am", "just", "testing"],
               ["Hey,", "I", "am", "just", "testing."]]
    _s, hyps, _f, _a = run(ticks, decodes)
    typed = " ".join(h.stable_delta for h in hyps)
    assert "Hey, I am just testing" in typed
    assert typed.count("message") == 1


def test_prompt_keeps_sentence_marks_committed_on_their_own():
    s = StreamingSession(transcriber=FakeTranscriber([]), read_audio=lambda: np.zeros(0, np.float32),
                         on_hypothesis=lambda h: None, on_finished=lambda e: None,
                         on_auto_stop=lambda: None)
    s._emit(["the", "report"], ["."])
    s._emit([".", "Can", "you"], [])
    assert s._prompt() == "the report. Can you"
