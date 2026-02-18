"""Tests for bridge training and dictionary update functionality."""

import json
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from shuper_whisper.bridge import WindowAPI
from shuper_whisper.dictionary import WordDictionary


@pytest.fixture
def mock_app(tmp_path):
    """Create a mock app with real dictionary and mock recorder/transcriber."""
    app = MagicMock()
    app.dictionary = WordDictionary(path=str(tmp_path / "dict.json"))
    app.recorder = MagicMock()
    app.recorder.stop_recording.return_value = np.zeros(16000, dtype=np.float32)
    app.transcriber = MagicMock()
    return app


@pytest.fixture
def api(mock_app):
    window = MagicMock()
    a = WindowAPI(window=window)
    a.set_app_instance(mock_app)
    return a


class TestNormalize:
    def test_strips_punctuation(self):
        assert WindowAPI._normalize("mackinaw.") == "mackinaw"

    def test_strips_trailing_comma(self):
        assert WindowAPI._normalize("hello,") == "hello"

    def test_strips_quotes(self):
        assert WindowAPI._normalize('"mackinaw"') == "mackinaw"

    def test_lowercases(self):
        assert WindowAPI._normalize("MacOS") == "macos"

    def test_preserves_spaces(self):
        assert WindowAPI._normalize("cube control") == "cube control"

    def test_strips_mixed_punctuation(self):
        assert WindowAPI._normalize("Hello, world!") == "hello world"


class TestTrainWordPassesDictionaryHints:
    def test_passes_initial_prompt_and_hotwords(self, api, mock_app):
        mock_app.dictionary.add("kubectl", "cube control")
        mock_app.transcriber.transcribe.return_value = "kubectl"

        api.train_word("kubectl")

        calls = mock_app.transcriber.transcribe.call_args_list
        assert len(calls) == 3
        for call in calls:
            assert call.kwargs["initial_prompt"] is not None
            assert "kubectl" in call.kwargs["initial_prompt"]
            assert "cube control" in call.kwargs["initial_prompt"]
            assert call.kwargs["hotwords"] is not None
            assert "kubectl" in call.kwargs["hotwords"]

    def test_passes_none_when_dictionary_empty(self, api, mock_app):
        mock_app.transcriber.transcribe.return_value = "hello"

        api.train_word("hello")

        calls = mock_app.transcriber.transcribe.call_args_list
        for call in calls:
            assert call.kwargs["initial_prompt"] is None
            assert call.kwargs["hotwords"] is None


class TestTrainWordLearning:
    def test_already_recognized_no_hint_change(self, api, mock_app):
        """If Whisper already gets it right, don't change the phonetic hint."""
        mock_app.dictionary.add("pytest")
        mock_app.transcriber.transcribe.return_value = "pytest"

        result = api.train_word("pytest")

        assert result["success"] is True
        assert result["alreadyRecognized"] is True
        assert result["learnedHint"] is None
        assert result["matchCount"] == 3
        assert mock_app.dictionary.entries[0].trained is True

    def test_learns_phonetic_hint_from_misheard(self, api, mock_app):
        """If Whisper mishears consistently, auto-set phonetic hint."""
        mock_app.dictionary.add("mackinac")
        mock_app.transcriber.transcribe.side_effect = [
            "mackinaw.",
            "mackinaw",
            "mackinaw!",
        ]

        result = api.train_word("mackinac")

        assert result["success"] is True
        assert result["alreadyRecognized"] is False
        assert result["learnedHint"] == "mackinaw"
        # Phonetic hint should be auto-updated
        assert mock_app.dictionary.entries[0].phonetic == "mackinaw"
        assert mock_app.dictionary.entries[0].trained is True

    def test_learns_most_common_transcription(self, api, mock_app):
        """Picks the most frequent mishearing as the hint."""
        mock_app.dictionary.add("kubectl")
        mock_app.transcriber.transcribe.side_effect = [
            "cube control",
            "cube control",
            "q control",
        ]

        result = api.train_word("kubectl")

        assert result["learnedHint"] == "cube control"
        assert mock_app.dictionary.entries[0].phonetic == "cube control"

    def test_partial_match_still_learns(self, api, mock_app):
        """Even with some matches, learns from the misheard ones."""
        mock_app.dictionary.add("mackinac")
        mock_app.transcriber.transcribe.side_effect = [
            "mackinac",
            "mackinaw",
            "mackinaw",
        ]

        result = api.train_word("mackinac")

        # 1 match out of 3, not "already recognized"
        assert result["alreadyRecognized"] is False
        assert result["learnedHint"] == "mackinaw"

    def test_always_marks_trained(self, api, mock_app):
        """Training always marks the word as trained."""
        mock_app.dictionary.add("kubectl")
        mock_app.transcriber.transcribe.return_value = "cube control"

        result = api.train_word("kubectl")

        assert result["success"] is True
        assert mock_app.dictionary.entries[0].trained is True

    def test_punctuation_stripped_for_matching(self, api, mock_app):
        """Whisper trailing punctuation shouldn't cause a mismatch."""
        mock_app.dictionary.add("mackinaw")
        mock_app.transcriber.transcribe.return_value = "mackinaw."

        result = api.train_word("mackinaw")

        assert result["alreadyRecognized"] is True
        assert result["matchCount"] == 3

    def test_returns_per_round_results(self, api, mock_app):
        mock_app.dictionary.add("test")
        mock_app.transcriber.transcribe.side_effect = ["test", "tess", "test"]

        result = api.train_word("test")

        assert len(result["results"]) == 3
        assert result["results"][0] == {"round": 1, "transcribed": "test", "success": True}
        assert result["results"][1] == {"round": 2, "transcribed": "tess", "success": False}
        assert result["results"][2] == {"round": 3, "transcribed": "test", "success": True}

    def test_records_3_seconds_per_round(self, api, mock_app):
        mock_app.dictionary.add("test")
        mock_app.transcriber.transcribe.return_value = "test"

        with patch("shuper_whisper.bridge.time") as mock_time:
            mock_time.sleep = MagicMock()
            api.train_word("test")

            sleep_calls = [c[0][0] for c in mock_time.sleep.call_args_list]
            assert sleep_calls.count(3) == 3
            assert sleep_calls.count(1) == 2


class TestTrainWordStatusPush:
    def test_pushes_all_status_updates(self, api, mock_app):
        mock_app.dictionary.add("test")
        mock_app.transcriber.transcribe.return_value = "test"

        api.train_word("test")

        js_calls = [c[0][0] for c in api._window.evaluate_js.call_args_list]
        statuses = []
        for call in js_calls:
            json_str = call.replace("window.__onTrainingStatus(", "").rstrip(")")
            data = json.loads(json_str)
            statuses.append(data["status"])

        assert statuses.count("recording") == 3
        assert statuses.count("transcribing") == 3
        assert statuses.count("round_done") == 3
        assert statuses.count("done") == 1

    def test_round_done_includes_round_number(self, api, mock_app):
        mock_app.dictionary.add("test")
        mock_app.transcriber.transcribe.return_value = "test"

        api.train_word("test")

        js_calls = [c[0][0] for c in api._window.evaluate_js.call_args_list]
        round_dones = []
        for call in js_calls:
            json_str = call.replace("window.__onTrainingStatus(", "").rstrip(")")
            data = json.loads(json_str)
            if data["status"] == "round_done":
                round_dones.append(data)

        assert len(round_dones) == 3
        for i, rd in enumerate(round_dones):
            assert rd["round"] == i + 1
            assert rd["totalRounds"] == 3


class TestTrainWordEdgeCases:
    def test_empty_word(self, api):
        result = api.train_word("")
        assert result["success"] is False

    def test_no_app(self):
        a = WindowAPI(window=MagicMock())
        result = a.train_word("test")
        assert result["success"] is False

    def test_transcriber_error(self, api, mock_app):
        mock_app.dictionary.add("test")
        mock_app.transcriber.transcribe.side_effect = RuntimeError("model error")

        result = api.train_word("test")

        assert result["success"] is False
        assert "model error" in result["error"]

    def test_case_insensitive_match(self, api, mock_app):
        mock_app.dictionary.add("MacOS")
        mock_app.transcriber.transcribe.return_value = "macos"

        result = api.train_word("MacOS")

        assert result["success"] is True
        assert result["alreadyRecognized"] is True


class TestUpdateWord:
    def test_update_existing_word(self, api, mock_app):
        mock_app.dictionary.add("kubctl", "cube control")
        result = api.update_word("kubctl", "kubectl", "cube control")
        assert result["success"] is True
        assert mock_app.dictionary.entries[0].word == "kubectl"
        assert mock_app.dictionary.entries[0].phonetic == "cube control"

    def test_update_phonetic_only(self, api, mock_app):
        mock_app.dictionary.add("kubectl")
        result = api.update_word("kubectl", "kubectl", "cube control")
        assert result["success"] is True
        assert mock_app.dictionary.entries[0].phonetic == "cube control"

    def test_update_nonexistent_word(self, api, mock_app):
        result = api.update_word("nope", "still_nope")
        assert result["success"] is False

    def test_update_empty_old_word(self, api):
        result = api.update_word("", "new")
        assert result["success"] is False

    def test_update_empty_new_word(self, api):
        result = api.update_word("old", "")
        assert result["success"] is False

    def test_update_no_app(self):
        a = WindowAPI(window=MagicMock())
        result = a.update_word("old", "new")
        assert result["success"] is False
