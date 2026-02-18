"""Tests for the word dictionary."""

import json

import pytest

from shuper_whisper.dictionary import DictionaryEntry, WordDictionary


@pytest.fixture
def dict_path(tmp_path):
    return str(tmp_path / "dictionary.json")


@pytest.fixture
def dictionary(dict_path):
    return WordDictionary(path=dict_path)


class TestDictionaryCRUD:
    def test_add_word(self, dictionary):
        entry = dictionary.add("kubectl")
        assert entry.word == "kubectl"
        assert entry.phonetic == ""
        assert entry.trained is False

    def test_add_word_with_phonetic(self, dictionary):
        entry = dictionary.add("kubectl", "cube control")
        assert entry.phonetic == "cube control"

    def test_add_duplicate_updates_phonetic(self, dictionary):
        dictionary.add("kubectl", "old hint")
        entry = dictionary.add("kubectl", "cube control")
        assert entry.phonetic == "cube control"
        assert len(dictionary.entries) == 1

    def test_add_case_insensitive_match(self, dictionary):
        dictionary.add("Kubectl")
        dictionary.add("kubectl", "hint")
        assert len(dictionary.entries) == 1

    def test_remove_word(self, dictionary):
        dictionary.add("kubectl")
        assert dictionary.remove("kubectl") is True
        assert len(dictionary.entries) == 0

    def test_remove_nonexistent(self, dictionary):
        assert dictionary.remove("nope") is False

    def test_remove_case_insensitive(self, dictionary):
        dictionary.add("Kubectl")
        assert dictionary.remove("kubectl") is True

    def test_update_word(self, dictionary):
        dictionary.add("kubctl", "cube control")
        assert dictionary.update("kubctl", "kubectl", "cube control") is True
        assert dictionary.entries[0].word == "kubectl"

    def test_update_nonexistent(self, dictionary):
        assert dictionary.update("nope", "still_nope") is False

    def test_entries_returns_copy(self, dictionary):
        dictionary.add("test")
        entries = dictionary.entries
        entries.clear()
        assert len(dictionary.entries) == 1

    def test_mark_trained(self, dictionary):
        dictionary.add("kubectl")
        dictionary.mark_trained("kubectl")
        assert dictionary.entries[0].trained is True


class TestDictionaryPersistence:
    def test_save_and_load(self, dict_path):
        d1 = WordDictionary(path=dict_path)
        d1.add("kubectl", "cube control")
        d1.add("pytest", "pie test")
        d1.mark_trained("kubectl")

        d2 = WordDictionary(path=dict_path)
        assert len(d2.entries) == 2
        assert d2.entries[0].word == "kubectl"
        assert d2.entries[0].phonetic == "cube control"
        assert d2.entries[0].trained is True
        assert d2.entries[1].word == "pytest"

    def test_load_empty_file(self, dict_path):
        with open(dict_path, "w") as f:
            f.write("[]")
        d = WordDictionary(path=dict_path)
        assert len(d.entries) == 0

    def test_load_corrupt_file(self, dict_path):
        with open(dict_path, "w") as f:
            f.write("not json")
        d = WordDictionary(path=dict_path)
        assert len(d.entries) == 0

    def test_load_nonexistent_file(self, tmp_path):
        d = WordDictionary(path=str(tmp_path / "nope.json"))
        assert len(d.entries) == 0


class TestTranscriberIntegration:
    def test_initial_prompt_empty(self, dictionary):
        assert dictionary.get_initial_prompt() == ""

    def test_initial_prompt_simple(self, dictionary):
        dictionary.add("kubectl")
        prompt = dictionary.get_initial_prompt()
        assert "kubectl" in prompt
        assert prompt.startswith("Vocabulary:")

    def test_initial_prompt_with_phonetic(self, dictionary):
        dictionary.add("kubectl", "cube control")
        prompt = dictionary.get_initial_prompt()
        assert "kubectl (cube control)" in prompt

    def test_initial_prompt_multiple(self, dictionary):
        dictionary.add("kubectl")
        dictionary.add("pytest")
        prompt = dictionary.get_initial_prompt()
        assert "kubectl" in prompt
        assert "pytest" in prompt

    def test_hotwords_empty(self, dictionary):
        assert dictionary.get_hotwords() == ""

    def test_hotwords_simple(self, dictionary):
        dictionary.add("kubectl")
        dictionary.add("pytest")
        hw = dictionary.get_hotwords()
        assert "kubectl" in hw
        assert "pytest" in hw


class TestDictionaryEntry:
    def test_defaults(self):
        e = DictionaryEntry(word="test")
        assert e.phonetic == ""
        assert e.trained is False

    def test_full_init(self):
        e = DictionaryEntry(word="test", phonetic="hint", trained=True)
        assert e.word == "test"
        assert e.phonetic == "hint"
        assert e.trained is True
