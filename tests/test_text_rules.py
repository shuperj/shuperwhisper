"""Tests for deterministic dictation cleanup."""

import pytest

from shuper_whisper.text_rules import clean, join


class TestWhitespace:
    def test_collapses_double_spaces(self):
        assert clean("Hello  there.   How are you?") == "Hello there. How are you?"

    def test_strips_edges(self):
        assert clean("  Hello.  ") == "Hello."

    def test_no_space_before_punctuation(self):
        assert clean("Hello , world .") == "Hello, world."


class TestDashes:
    @pytest.mark.parametrize("raw", [
        "I went home — then I slept.",
        "I went home—then I slept.",
        "I went home – then I slept.",
        "I went home -- then I slept.",
        "I went home - then I slept.",
    ])
    def test_dashes_become_commas(self, raw):
        assert clean(raw) == "I went home, then I slept."

    def test_hyphenated_words_untouched(self):
        assert clean("A well-known follow-up.") == "A well-known follow-up."

    def test_trailing_dash_dropped(self):
        assert clean("I was going to —") == "I was going to"


class TestEllipses:
    def test_trailing_ellipsis_removed(self):
        assert clean("I went to the...") == "I went to the"

    def test_unicode_ellipsis_removed(self):
        assert clean("I went to the…") == "I went to the"

    def test_mid_ellipsis_before_lowercase_is_a_space(self):
        assert clean("I was thinking... maybe not.") == "I was thinking maybe not."

    def test_mid_ellipsis_before_capital_ends_sentence(self):
        assert clean("I was thinking... Maybe not.") == "I was thinking. Maybe not."


class TestFillers:
    def test_leading_filler(self):
        assert clean("Um, so we should go.") == "so we should go."

    def test_filler_between_commas(self):
        assert clean("I think, uh, we should go.") == "I think we should go."

    def test_filler_sentence(self):
        assert clean("Okay. Um. Next thing.") == "Okay. Next thing."

    def test_keeps_like_and_just(self):
        assert clean("I just like it.") == "I just like it."

    def test_does_not_eat_words_containing_fillers(self):
        assert clean("The umbrella is human.") == "The umbrella is human."


class TestCommands:
    def test_period(self):
        assert clean("send it today period") == "send it today."

    def test_comma(self):
        assert clean("hello comma world") == "hello, world"

    def test_question_mark(self):
        assert clean("are you coming question mark") == "are you coming?"

    def test_exclamation(self):
        assert clean("great exclamation point") == "great!"

    def test_colon(self):
        assert clean("note colon buy milk") == "note: buy milk"

    def test_whisper_punctuated_command(self):
        assert clean("Send it today, period.") == "Send it today."

    def test_new_line(self):
        assert clean("Dear Dana, new line thanks for the update.") == "Dear Dana,\nThanks for the update."

    def test_new_paragraph(self):
        assert clean("First point. New paragraph. Second point.") == "First point.\n\nSecond point."

    def test_capitalises_after_command_period(self):
        assert clean("done period next one") == "done. Next one"


class TestReplacements:
    def test_whole_word_case_insensitive(self):
        assert clean("I drove to mackinaw today.", [("mackinaw", "Mackinac")]) == "I drove to Mackinac today."

    def test_not_inside_other_words(self):
        assert clean("Mackinawville", [("mackinaw", "Mackinac")]) == "Mackinawville"

    def test_multi_word(self):
        assert clean("open shoe per whisper", [("shoe per whisper", "ShuperWhisper")]) == "open ShuperWhisper"

    def test_identity_pairs_ignored(self):
        assert clean("Dana", [("dana", "Dana")]) == "Dana"


class TestJoin:
    def test_unknown_context_capitalises_without_space(self):
        assert join("hello there.", None) == "Hello there."

    def test_empty_field(self):
        assert join("hello.", "") == "Hello."

    def test_after_newline(self):
        assert join("hello.", "Dear Dana,\n") == "Hello."

    def test_after_sentence_end(self):
        assert join("next thing.", "Done.") == " Next thing."

    def test_after_sentence_end_and_space(self):
        assert join("next thing.", "Done. ") == "Next thing."

    def test_mid_sentence_softens_common_starter(self):
        assert join("Then we left.", "We ate dinner") == " then we left."

    def test_mid_sentence_keeps_proper_noun(self):
        assert join("Dana left.", "We ate with") == " Dana left."

    def test_mid_sentence_keeps_i(self):
        assert join("I left.", "Then") == " I left."

    def test_after_opening_bracket(self):
        assert join("see below)", "(") == "see below)"

    def test_punctuation_attaches(self):
        assert join(", and then", "Hello") == ", and then"

    def test_leading_newline_untouched(self):
        assert join("\nThanks.", "Hi") == "\nThanks."

    def test_empty_text(self):
        assert join("", "Hello") == ""


class TestPartial:
    def test_partial_keeps_trailing_comma(self):
        assert clean("I think,", final=False) == "I think,"

    def test_final_drops_trailing_comma(self):
        assert clean("I think,") == "I think"

    def test_partial_dash_becomes_trailing_comma(self):
        assert clean("I went home —", final=False) == "I went home,"
