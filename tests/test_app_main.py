"""Tests for the shuper_whisper.app:main gui-scripts entry point."""

import pytest
from unittest.mock import MagicMock, patch

import shuper_whisper.app as app_module


class TestMainEntryPoint:
    def test_main_exists_and_is_callable(self):
        assert callable(app_module.main)

    def test_main_list_devices_mode(self):
        # Let the real SystemExit propagate. Patching sys.exit makes main()
        # fall through into load_config() and the real TrayController, whose
        # run() blocks forever and hangs the suite.
        with patch.object(app_module, "list_devices") as mock_list_devices, \
                patch.object(app_module, "_enable_dpi_awareness"), \
                patch.object(app_module, "_load_env"), \
                patch("sys.argv", ["shuper-whisper", "--list-devices"]):
            with pytest.raises(SystemExit) as excinfo:
                app_module.main()

        mock_list_devices.assert_called_once()
        assert excinfo.value.code == 0

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


class TestPackagedEntryPointParity:
    """Behaviours that must not drift back out of app:main (issue #11).

    These were previously only in main.py's own main(), which nothing packaged
    calls -- so the installed app never declared DPI awareness and never loaded
    the .env that supplies ANTHROPIC_API_KEY.
    """

    def test_main_enables_dpi_awareness_and_loads_env(self):
        mock_config = MagicMock()
        mock_tray_module = MagicMock()

        with patch.object(app_module, "load_config", return_value=mock_config), \
                patch.object(app_module, "_enable_dpi_awareness") as mock_dpi, \
                patch.object(app_module, "_load_env") as mock_env, \
                patch("sys.argv", ["shuper-whisper"]), \
                patch.dict("sys.modules", {"shuper_whisper.tray": mock_tray_module}):
            app_module.main()

        mock_dpi.assert_called_once()
        mock_env.assert_called_once()

    def test_env_is_loaded_before_config_is_read(self):
        """Config/UI must not run before the API keys are in os.environ."""
        calls = []
        mock_tray_module = MagicMock()

        with patch.object(app_module, "_enable_dpi_awareness",
                          side_effect=lambda: calls.append("dpi")), \
                patch.object(app_module, "_load_env",
                             side_effect=lambda: calls.append("env")), \
                patch.object(app_module, "load_config",
                             side_effect=lambda: calls.append("config") or MagicMock()), \
                patch("sys.argv", ["shuper-whisper"]), \
                patch.dict("sys.modules", {"shuper_whisper.tray": mock_tray_module}):
            app_module.main()

        assert calls == ["dpi", "env", "config"]

    def test_list_devices_still_short_circuits_before_config(self):
        with patch.object(app_module, "list_devices") as mock_list, \
                patch.object(app_module, "_enable_dpi_awareness"), \
                patch.object(app_module, "_load_env"), \
                patch.object(app_module, "load_config") as mock_config, \
                patch("sys.argv", ["shuper-whisper", "--list-devices"]):
            with pytest.raises(SystemExit) as excinfo:
                app_module.main()

        mock_list.assert_called_once()
        assert excinfo.value.code == 0
        mock_config.assert_not_called()
