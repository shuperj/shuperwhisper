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


class TestOverlayMultiMonitor:
    def test_position_window_centers_on_active_monitor(self):
        o = RecordingOverlay(position="top_center")
        o._hwnd = 12345
        o._mode = "hold"

        from unittest.mock import patch, MagicMock

        with patch.object(
            RecordingOverlay,
            "_get_active_monitor_work_area",
            return_value=(1920, 0, 1920, 1080),
        ), patch("ctypes.windll.user32.SetWindowPos") as mock_swp:
            o._position_window()

            mock_swp.assert_called_once()
            args = mock_swp.call_args[0]
            x, y = args[2], args[3]
            expected_x = 1920 + (1920 - RecordingOverlay.WINDOW_W) // 2
            assert x == expected_x
            assert y == 0 + 80  # top_center offset

    def test_position_center_on_secondary_monitor(self):
        o = RecordingOverlay(position="center")
        o._hwnd = 12345
        o._mode = "toggle"

        from unittest.mock import patch

        with patch.object(
            RecordingOverlay,
            "_get_active_monitor_work_area",
            return_value=(1920, 0, 2560, 1440),
        ), patch("ctypes.windll.user32.SetWindowPos") as mock_swp:
            o._position_window()

            args = mock_swp.call_args[0]
            x, y = args[2], args[3]
            expected_x = 1920 + (2560 - RecordingOverlay.WINDOW_W) // 2
            expected_y = 0 + (1440 - RecordingOverlay.WINDOW_H_TOGGLE) // 2
            assert x == expected_x
            assert y == expected_y

    def test_position_bottom_center_respects_work_area(self):
        o = RecordingOverlay(position="bottom_center")
        o._hwnd = 12345
        o._mode = "hold"

        from unittest.mock import patch

        # Work area height 1040 (40px taskbar)
        with patch.object(
            RecordingOverlay,
            "_get_active_monitor_work_area",
            return_value=(0, 0, 1920, 1040),
        ), patch("ctypes.windll.user32.SetWindowPos") as mock_swp:
            o._position_window()

            args = mock_swp.call_args[0]
            y = args[3]
            expected_y = 0 + 1040 - RecordingOverlay.WINDOW_H_HOLD - 100
            assert y == expected_y

    def test_no_hwnd_is_noop(self):
        o = RecordingOverlay()
        o._hwnd = None

        from unittest.mock import patch

        with patch("ctypes.windll.user32.SetWindowPos") as mock_swp:
            o._position_window()
            mock_swp.assert_not_called()

    def test_primary_monitor_offset_at_origin(self):
        o = RecordingOverlay(position="top_center")
        o._hwnd = 12345
        o._mode = "hold"

        from unittest.mock import patch

        with patch.object(
            RecordingOverlay,
            "_get_active_monitor_work_area",
            return_value=(0, 0, 1920, 1080),
        ), patch("ctypes.windll.user32.SetWindowPos") as mock_swp:
            o._position_window()

            args = mock_swp.call_args[0]
            x, y = args[2], args[3]
            expected_x = (1920 - RecordingOverlay.WINDOW_W) // 2
            assert x == expected_x
            assert y == 80


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
