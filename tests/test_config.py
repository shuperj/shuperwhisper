"""Tests for the slimmed-down config."""

import json

from shuper_whisper.config import (
    VALID_COMPUTE,
    VALID_OVERLAY_POSITIONS,
    AppConfig,
    load_config,
    save_config,
)


class TestDefaults:
    def test_defaults(self):
        c = AppConfig()
        assert c.hotkey == "ctrl+shift+space"
        assert c.model_size == "auto"
        assert c.input_device is None
        assert c.language == "en"
        assert c.overlay_position == "top_center"
        assert c.compute == "auto"

    def test_removed_fields_are_gone(self):
        d = AppConfig().to_dict()
        for key in ("format_mode", "email_tone", "prompt_detail", "hotkey_mode",
                    "smart_spacing", "bullet_mode", "email_mode",
                    "accent_color", "bg_color"):
            assert key not in d


class TestValidate:
    def test_bad_model_resets_to_auto(self):
        c = AppConfig(model_size="huge")
        c.validate()
        assert c.model_size == "auto"

    def test_turbo_is_valid(self):
        c = AppConfig(model_size="large-v3-turbo")
        c.validate()
        assert c.model_size == "large-v3-turbo"

    def test_empty_hotkey_resets(self):
        c = AppConfig(hotkey="")
        c.validate()
        assert c.hotkey == "ctrl+shift+space"

    def test_unknown_language_resets(self):
        c = AppConfig(language="xx")
        c.validate()
        assert c.language == "en"

    def test_bad_overlay_position_resets(self):
        c = AppConfig(overlay_position="nowhere")
        c.validate()
        assert c.overlay_position == "top_center"

    def test_valid_positions_kept(self):
        for pos in VALID_OVERLAY_POSITIONS:
            c = AppConfig(overlay_position=pos)
            c.validate()
            assert c.overlay_position == pos

    def test_compute_values(self):
        for value in VALID_COMPUTE:
            c = AppConfig(compute=value)
            c.validate()
            assert c.compute == value
        c = AppConfig(compute="tpu")
        c.validate()
        assert c.compute == "auto"


class TestInputDevice:
    def test_none_is_default(self):
        c = AppConfig(input_device=None)
        c.validate()
        assert c.input_device is None

    def test_ref_kept(self):
        ref = {"name": "Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO)", "hostapi": "Windows WASAPI"}
        c = AppConfig(input_device=dict(ref))
        c.validate()
        assert c.input_device == ref

    def test_ref_without_hostapi(self):
        c = AppConfig(input_device={"name": "Mic"})
        c.validate()
        assert c.input_device == {"name": "Mic", "hostapi": None}

    def test_legacy_int_kept_for_migration(self):
        c = AppConfig(input_device=75)
        c.validate()
        assert c.input_device == 75

    def test_bool_is_not_an_index(self):
        c = AppConfig(input_device=True)
        c.validate()
        assert c.input_device is None

    def test_legacy_name_string_becomes_ref(self):
        c = AppConfig(input_device="Mic")
        c.validate()
        assert c.input_device == {"name": "Mic", "hostapi": None}

    def test_garbage_becomes_default(self):
        for bad in ({"hostapi": "MME"}, {"name": ""}, [], 3.5, ""):
            c = AppConfig(input_device=bad)
            c.validate()
            assert c.input_device is None, bad


class TestSaveLoad:
    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "config.json")
        ref = {"name": "Mic", "hostapi": "MME"}
        save_config(AppConfig(hotkey="f9", model_size="small", input_device=ref,
                              language="de", overlay_position="center", compute="cpu"), path)
        loaded = load_config(path)
        assert (loaded.hotkey, loaded.model_size, loaded.input_device,
                loaded.language, loaded.overlay_position, loaded.compute) == (
            "f9", "small", ref, "de", "center", "cpu")

    def test_old_config_keys_ignored(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w") as f:
            json.dump({"hotkey": "f16", "format_mode": "ai_prompt", "email_tone": 5,
                       "accent_color": "#000000", "input_device": 75}, f)
        loaded = load_config(path)
        assert loaded.hotkey == "f16"
        assert loaded.input_device == 75
        assert not hasattr(loaded, "format_mode")

    def test_missing_file_gives_defaults(self, tmp_path):
        assert load_config(str(tmp_path / "nope.json")).model_size == "auto"
