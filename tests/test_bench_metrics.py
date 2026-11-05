"""The benchmark's scoring (benchmarks/metrics.py)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "benchmarks"))
pytest.importorskip("regex")
pytest.importorskip("more_itertools")
from metrics import invented, wer, word_ops  # noqa: E402

HOT = "Mackinaw, claude.md, shuper, onebynine, gitea"


def test_wer_counts_every_kind_of_error():
    assert wer("the cat sat on the mat", "the cat sat on the mat") == (0, 6)
    assert wer("the cat sat on the mat", "the bat sat the mat today") == (3, 6)


def test_word_ops_align_in_order():
    assert word_ops("a b c", "a x c d") == [("=", "a", "a"), ("~", "b", "x"), ("=", "c", "c"),
                                            ("+", "", "d")]


def test_made_up_ending_is_invented():
    got = invented("I sent it over on Monday.", "I sent it over Monday. I'm going to get a bit")
    assert got == ["i", "am", "going", "to", "get", "a", "bit"]


def test_seam_repeat_is_invented():
    assert invented("once we've run it", "once we once we've run it") == ["once", "we"]
    assert invented("open it the list", "open it it the list") == ["it"]


def test_dictionary_word_in_place_of_another_is_invented():
    assert invented("try moving the whole thing", "try gitea the whole thing", HOT) == ["gitea"]


def test_compound_split_and_misspelling_are_not_invented():
    assert invented("through pywebview", "through pi web view", HOT) == []
    assert invented("through Voicemeeter", "through voice meter", HOT) == []
    assert invented("push to gitea tonight", "push to gitty tonight", HOT) == []


def test_ordinary_misheard_word_is_not_invented():
    assert invented("the settings window loads", "the settings windows load", HOT) == []
