"""Tests for the shuper_whisper.app:main gui-scripts entry point."""

from unittest.mock import MagicMock, patch

import shuper_whisper.app as app_module


class TestMainEntryPoint:
    def test_main_exists_and_is_callable(self):
        assert callable(app_module.main)

    def test_main_list_devices_mode(self):
        with patch.object(app_module, "list_devices") as mock_list_devices, \
                patch("sys.argv", ["shuper-whisper", "--list-devices"]), \
                patch("sys.exit") as mock_exit:
            app_module.main()

        mock_list_devices.assert_called_once()
        mock_exit.assert_called_once_with(0)

    def test_main_console_mode_runs_app(self):
        mock_config = MagicMock()
        mock_app = MagicMock()

        with patch.object(app_module, "load_config", return_value=mock_config), \
                patch.object(app_module, "ShuperWhisperApp", return_value=mock_app) as mock_cls, \
                patch("sys.argv", ["shuper-whisper", "--console"]):
            app_module.main()

        mock_cls.assert_called_once_with(mock_config)
        mock_app.run.assert_called_once()

    def test_main_default_mode_starts_tray(self):
        mock_config = MagicMock()
        mock_tray_controller = MagicMock()
        mock_tray_module = MagicMock()
        mock_tray_module.TrayController.return_value = mock_tray_controller

        with patch.object(app_module, "load_config", return_value=mock_config), \
                patch("sys.argv", ["shuper-whisper"]), \
                patch.dict("sys.modules", {"shuper_whisper.tray": mock_tray_module}):
            app_module.main()

        mock_tray_module.TrayController.assert_called_once_with(mock_config)
        mock_tray_controller.run.assert_called_once()
