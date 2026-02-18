"""Tests for the text formatter (template fallback only - API tested manually)."""

import pytest

from shuper_whisper.formatter import TextFormatter


@pytest.fixture
def formatter():
    f = TextFormatter()
    # Force template-only mode for deterministic tests
    f._api_available = False
    return f


class TestNormalMode:
    def test_returns_unchanged(self, formatter):
        assert formatter.format_text("hello world", "normal") == "hello world"

    def test_empty_returns_empty(self, formatter):
        assert formatter.format_text("", "normal") == ""

    def test_none_handled(self, formatter):
        assert formatter.format_text("", "professional_email") == ""


class TestProfessionalEmailTemplate:
    def test_capitalizes_sentences(self, formatter):
        result = formatter.format_text("hello there. how are you", "professional_email")
        assert result.startswith("Hello there")
        assert result.endswith(".")

    def test_adds_period(self, formatter):
        result = formatter.format_text("please review the document", "professional_email")
        assert result.endswith(".")

    def test_preserves_existing_period(self, formatter):
        result = formatter.format_text("Thank you.", "professional_email")
        assert not result.endswith("..")

    def test_multiple_sentences(self, formatter):
        result = formatter.format_text(
            "first sentence. second sentence", "professional_email"
        )
        assert "First sentence" in result
        assert "Second sentence" in result


class TestProfessionalEmailTone:
    def test_default_tone_no_greeting(self, formatter):
        result = formatter.format_text("hello there", "professional_email", email_tone=3)
        assert "Dear" not in result

    def test_high_formality_adds_greeting(self, formatter):
        result = formatter.format_text(
            "please review the document", "professional_email", email_tone=5
        )
        assert "Dear" in result
        assert "Best regards" in result

    def test_low_formality_no_greeting(self, formatter):
        result = formatter.format_text(
            "please review the document", "professional_email", email_tone=1
        )
        assert "Dear" not in result

    def test_tone_threshold_at_4(self, formatter):
        result = formatter.format_text(
            "please review", "professional_email", email_tone=4
        )
        assert "Dear" in result


class TestAIPromptTemplate:
    def test_removes_filler_words(self, formatter):
        result = formatter.format_text(
            "I um basically want to like create a function", "ai_prompt"
        )
        assert "um" not in result
        assert "basically" not in result
        assert "like" not in result

    def test_preserves_content(self, formatter):
        result = formatter.format_text("create a REST API endpoint", "ai_prompt")
        assert "REST API endpoint" in result

    def test_removes_leading_filler(self, formatter):
        result = formatter.format_text("um write a function", "ai_prompt")
        assert not result.lower().startswith("um")

    def test_collapses_double_spaces(self, formatter):
        result = formatter.format_text(
            "I just want to sort of do this", "ai_prompt"
        )
        assert "  " not in result


class TestAIPromptDetail:
    def test_default_detail_no_prefix(self, formatter):
        result = formatter.format_text(
            "create a REST API", "ai_prompt", prompt_detail=3
        )
        assert not result.startswith("Task:")

    def test_high_detail_adds_prefix(self, formatter):
        result = formatter.format_text(
            "create a REST API", "ai_prompt", prompt_detail=5
        )
        assert result.startswith("Task:")

    def test_low_detail_concise(self, formatter):
        result = formatter.format_text(
            "create a REST API", "ai_prompt", prompt_detail=1
        )
        assert not result.startswith("Task:")

    def test_detail_threshold_at_4(self, formatter):
        result = formatter.format_text(
            "create a REST API", "ai_prompt", prompt_detail=4
        )
        assert result.startswith("Task:")


class TestFormatterInit:
    def test_api_flag_set(self):
        f = TextFormatter()
        # May or may not have API depending on env - just check it doesn't crash
        assert isinstance(f._api_available, bool)

    def test_unknown_mode_returns_original(self, formatter):
        result = formatter.format_text("hello", "unknown_mode")
        assert result == "hello"
