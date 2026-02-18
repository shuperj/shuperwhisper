"""Tests for smart text processing (unchanged module, verify no regressions)."""

import pytest

from shuper_whisper.smart_text import (
    apply_bullet_mode,
    apply_email_mode,
    apply_smart_spacing,
    process_text,
)


class TestSmartSpacing:
    def test_no_context_prepends_space(self):
        assert apply_smart_spacing(None, "hello") == " hello"

    def test_empty_context_prepends_space(self):
        assert apply_smart_spacing("", "hello") == " hello"

    def test_newline_context_capitalizes(self):
        assert apply_smart_spacing("foo\n", "hello") == "Hello"

    def test_whitespace_context_no_extra_space(self):
        assert apply_smart_spacing("foo ", "hello") == "hello"

    def test_sentence_ender_space_and_capitalize(self):
        assert apply_smart_spacing("Done.", "next") == " Next"
        assert apply_smart_spacing("What?", "really") == " Really"
        assert apply_smart_spacing("Wow!", "nice") == " Nice"

    def test_mid_word_adds_space(self):
        assert apply_smart_spacing("mid", "word") == " word"

    def test_empty_text_returns_empty(self):
        assert apply_smart_spacing("foo", "") == ""


class TestBulletMode:
    def test_basic_bullet(self):
        assert apply_bullet_mode(None, "item") == "- item"

    def test_after_newline(self):
        assert apply_bullet_mode("list:\n", "item") == "- item"

    def test_after_text_adds_newline(self):
        assert apply_bullet_mode("some text", "item") == "\n- item"

    def test_empty_text(self):
        assert apply_bullet_mode("foo", "") == ""


class TestEmailMode:
    def test_greeting_adds_double_newline(self):
        result = apply_email_mode("Hi John, please review")
        assert "\n\n" in result

    def test_signoff_adds_double_newline(self):
        result = apply_email_mode("Best regards")
        assert result.startswith("\n\n")

    def test_plain_text_unchanged(self):
        assert apply_email_mode("just normal text") == "just normal text"

    def test_empty(self):
        assert apply_email_mode("") == ""


class TestProcessText:
    def test_all_disabled(self):
        result = process_text("ctx", "hello", smart_spacing=False, bullet_mode=False, email_mode=False)
        assert result == "hello"

    def test_smart_spacing_only(self):
        result = process_text("word", "next", smart_spacing=True)
        assert result == " next"

    def test_bullet_takes_precedence_over_spacing(self):
        result = process_text("text", "item", smart_spacing=True, bullet_mode=True)
        assert result == "\n- item"

    def test_email_mode_applied(self):
        result = process_text(None, "Hi John, text", email_mode=True, smart_spacing=True)
        assert "\n\n" in result

    def test_empty_text(self):
        assert process_text("ctx", "", smart_spacing=True) == ""
