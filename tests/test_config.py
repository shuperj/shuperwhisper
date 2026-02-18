"""Tests for config module with new fields."""

import json
import os
import tempfile

import pytest

from shuper_whisper.config import (
    FORMAT_MODE_LABELS,
    FORMAT_MODE_ORDER,
    VALID_FORMAT_MODES,
    VALID_HOTKEY_MODES,
    VALID_OVERLAY_POSITIONS,
    AppConfig,
    load_config,
    save_config,
)


class TestAppConfigDefaults:
    def test_default_hotkey_mode(self):
        c = AppConfig()
        assert c.hotkey_mode == "hold"

    def test_default_format_mode(self):
        c = AppConfig()
        assert c.format_mode == "normal"

    def test_default_email_tone(self):
        c = AppConfig()
        assert c.email_tone == 3

    def test_default_prompt_detail(self):
        c = AppConfig()
        assert c.prompt_detail == 3

    def test_default_overlay_position(self):
        c = AppConfig()
        assert c.overlay_position == "top_center"

    def test_backward_compatible_defaults(self):
        c = AppConfig()
        assert c.hotkey == "ctrl+shift+space"
        assert c.model_size == "base"
        assert c.smart_spacing is True
        assert c.bullet_mode is False
        assert c.email_mode is False


class TestAppConfigValidation:
    def test_invalid_hotkey_mode_resets(self):
        c = AppConfig(hotkey_mode="invalid")
        c.validate()
        assert c.hotkey_mode == "hold"

    def test_invalid_format_mode_resets(self):
        c = AppConfig(format_mode="invalid")
        c.validate()
        assert c.format_mode == "normal"

    def test_invalid_overlay_position_resets(self):
        c = AppConfig(overlay_position="invalid")
        c.validate()
        assert c.overlay_position == "top_center"

    def test_email_tone_clamped_low(self):
        c = AppConfig(email_tone=0)
        c.validate()
        assert c.email_tone == 1

    def test_email_tone_clamped_high(self):
        c = AppConfig(email_tone=10)
        c.validate()
        assert c.email_tone == 5

    def test_prompt_detail_clamped_low(self):
        c = AppConfig(prompt_detail=0)
        c.validate()
        assert c.prompt_detail == 1

    def test_prompt_detail_clamped_high(self):
        c = AppConfig(prompt_detail=10)
        c.validate()
        assert c.prompt_detail == 5

    def test_valid_hotkey_modes_preserved(self):
        for mode in VALID_HOTKEY_MODES:
            c = AppConfig(hotkey_mode=mode)
            c.validate()
            assert c.hotkey_mode == mode

    def test_valid_format_modes_preserved(self):
        for mode in VALID_FORMAT_MODES:
            c = AppConfig(format_mode=mode)
            c.validate()
            assert c.format_mode == mode

    def test_valid_overlay_positions_preserved(self):
        for pos in VALID_OVERLAY_POSITIONS:
            c = AppConfig(overlay_position=pos)
            c.validate()
            assert c.overlay_position == pos

    def test_old_casual_text_format_mode_resets(self):
        c = AppConfig(format_mode="casual_text")
        c.validate()
        assert c.format_mode == "normal"


class TestConfigSaveLoad:
    def test_round_trip_new_fields(self, tmp_path):
        path = str(tmp_path / "config.json")
        c = AppConfig(
            hotkey_mode="toggle",
            format_mode="professional_email",
            email_tone=5,
            prompt_detail=1,
            overlay_position="center",
        )
        save_config(c, path)
        loaded = load_config(path)
        assert loaded.hotkey_mode == "toggle"
        assert loaded.format_mode == "professional_email"
        assert loaded.email_tone == 5
        assert loaded.prompt_detail == 1
        assert loaded.overlay_position == "center"

    def test_load_missing_new_fields_uses_defaults(self, tmp_path):
        path = str(tmp_path / "config.json")
        # Simulate old config without new fields
        old_config = {"hotkey": "f5", "model_size": "small"}
        with open(path, "w") as f:
            json.dump(old_config, f)
        loaded = load_config(path)
        assert loaded.hotkey == "f5"
        assert loaded.model_size == "small"
        assert loaded.hotkey_mode == "hold"
        assert loaded.format_mode == "normal"
        assert loaded.email_tone == 3
        assert loaded.prompt_detail == 3

    def test_load_nonexistent_file(self, tmp_path):
        path = str(tmp_path / "does_not_exist.json")
        loaded = load_config(path)
        assert loaded.hotkey_mode == "hold"

    def test_to_dict_includes_new_fields(self):
        c = AppConfig(hotkey_mode="toggle", email_tone=4)
        d = c.to_dict()
        assert d["hotkey_mode"] == "toggle"
        assert d["email_tone"] == 4
        assert "prompt_detail" in d
        assert "overlay_position" in d

    def test_old_casual_fields_ignored(self, tmp_path):
        path = str(tmp_path / "config.json")
        old_config = {
            "hotkey": "f16",
            "format_mode": "casual_text",
            "casual_level": 5,
            "emoji_level": 3,
            "shorthand_level": 2,
        }
        with open(path, "w") as f:
            json.dump(old_config, f)
        loaded = load_config(path)
        assert loaded.hotkey == "f16"
        assert loaded.format_mode == "normal"  # casual_text reset by validate()
        assert loaded.email_tone == 3  # default
        assert loaded.prompt_detail == 3  # default


class TestFormatModeConstants:
    def test_labels_cover_all_modes(self):
        for mode in VALID_FORMAT_MODES:
            assert mode in FORMAT_MODE_LABELS

    def test_order_matches_valid_modes(self):
        assert list(FORMAT_MODE_ORDER) == list(VALID_FORMAT_MODES)

    def test_three_format_modes(self):
        assert len(VALID_FORMAT_MODES) == 3

    def test_no_casual_text_mode(self):
        assert "casual_text" not in VALID_FORMAT_MODES
        assert "casual_text" not in FORMAT_MODE_LABELS
