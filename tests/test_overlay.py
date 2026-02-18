"""Tests for the overlay module (non-GUI logic only)."""

import pytest

from shuper_whisper.config import FORMAT_MODE_ORDER
from shuper_whisper.overlay import RecordingOverlay


class TestOverlayInit:
    def test_default_position(self):
        o = RecordingOverlay()
        assert o._position == "top_center"

    def test_custom_position(self):
        o = RecordingOverlay(position="center")
        assert o._position == "center"

    def test_initially_not_visible(self):
        o = RecordingOverlay()
        assert o.is_visible is False

    def test_default_format_mode(self):
        o = RecordingOverlay()
        assert o.format_mode == "normal"

    def test_default_state_is_recording(self):
        o = RecordingOverlay()
        assert o._state == "recording"


class TestFormatModeCycling:
    def test_cycle_down_from_normal(self):
        o = RecordingOverlay()
        o._format_mode = "normal"
        result = o.cycle_format_mode(1)
        assert result == "professional_email"

    def test_cycle_up_from_normal_wraps(self):
        o = RecordingOverlay()
        o._format_mode = "normal"
        result = o.cycle_format_mode(-1)
        assert result == "ai_prompt"

    def test_cycle_through_all_modes(self):
        o = RecordingOverlay()
        o._format_mode = "normal"
        modes = []
        for _ in range(len(FORMAT_MODE_ORDER)):
            mode = o.cycle_format_mode(1)
            modes.append(mode)
        # Should have cycled back to start
        assert modes[-1] == "normal"
        assert len(set(modes)) == len(FORMAT_MODE_ORDER)

    def test_cycle_calls_callback(self):
        called_with = []
        o = RecordingOverlay()
        o.set_on_format_change(lambda m: called_with.append(m))
        o._format_mode = "normal"
        o.cycle_format_mode(1)
        assert called_with == ["professional_email"]

    def test_format_mode_property(self):
        o = RecordingOverlay()
        o._format_mode = "ai_prompt"
        assert o.format_mode == "ai_prompt"


class TestOverlayPosition:
    def test_set_position(self):
        o = RecordingOverlay(position="top_center")
        o.set_position("bottom_center")
        assert o._position == "bottom_center"


class TestOverlayConstants:
    def test_bar_count_positive(self):
        assert RecordingOverlay.BAR_COUNT > 0

    def test_window_dimensions(self):
        assert RecordingOverlay.WINDOW_W > 0
        assert RecordingOverlay.WINDOW_H_HOLD > 0
        assert RecordingOverlay.WINDOW_H_TOGGLE > RecordingOverlay.WINDOW_H_HOLD


class TestOverlayColors:
    def test_hex_alpha_full(self):
        result = RecordingOverlay._hex_alpha("#ff4466", 1.0)
        assert result == "#ff4466"

    def test_hex_alpha_half(self):
        result = RecordingOverlay._hex_alpha("#ff4466", 0.5)
        assert result == "#7f2233"

    def test_hex_alpha_zero(self):
        result = RecordingOverlay._hex_alpha("#ff4466", 0.0)
        assert result == "#000000"
