"""Word dictionary for custom vocabulary and training."""

import json
import os
from dataclasses import asdict, dataclass


@dataclass
class DictionaryEntry:
    word: str
    phonetic: str = ""
    trained: bool = False


class WordDictionary:
    """Manages custom word/phrase dictionary for improved transcription."""

    def __init__(self, path: str | None = None):
        self._path = path or self._default_path()
        self._entries: list[DictionaryEntry] = []
        self.load()

    @staticmethod
    def _default_path() -> str:
        from .config import _default_dictionary_path
        return _default_dictionary_path()

    def load(self) -> None:
        try:
            with open(self._path, "r") as f:
                data = json.load(f)
            self._entries = [DictionaryEntry(**e) for e in data]
        except (FileNotFoundError, json.JSONDecodeError):
            self._entries = []

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with open(self._path, "w") as f:
            json.dump([asdict(e) for e in self._entries], f, indent=2)

    def add(self, word: str, phonetic: str = "") -> DictionaryEntry:
        """Add or update a word. Returns the entry."""
        for entry in self._entries:
            if entry.word.lower() == word.lower():
                entry.phonetic = phonetic
                self.save()
                return entry
        entry = DictionaryEntry(word=word, phonetic=phonetic)
        self._entries.append(entry)
        self.save()
        return entry

    def remove(self, word: str) -> bool:
        for i, entry in enumerate(self._entries):
            if entry.word.lower() == word.lower():
                self._entries.pop(i)
                self.save()
                return True
        return False

    def update(self, old_word: str, new_word: str, phonetic: str = "") -> bool:
        for entry in self._entries:
            if entry.word.lower() == old_word.lower():
                entry.word = new_word
                entry.phonetic = phonetic
                self.save()
                return True
        return False

    def mark_trained(self, word: str) -> None:
        for entry in self._entries:
            if entry.word.lower() == word.lower():
                entry.trained = True
                self.save()
                return

    @property
    def entries(self) -> list[DictionaryEntry]:
        return list(self._entries)

    def get_initial_prompt(self) -> str:
        """Build an initial_prompt string for the transcriber.

        Includes all dictionary words and phonetic hints to bias
        the model toward recognizing custom vocabulary.
        """
        if not self._entries:
            return ""
        parts = []
        for entry in self._entries:
            if entry.phonetic:
                parts.append(f"{entry.word} ({entry.phonetic})")
            else:
                parts.append(entry.word)
        return "Vocabulary: " + ", ".join(parts) + "."

    def get_hotwords(self) -> str:
        """Build a hotwords string for faster-whisper."""
        if not self._entries:
            return ""
        return ", ".join(entry.word for entry in self._entries)
