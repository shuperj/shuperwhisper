"""Tests for the packaged entry point, shuper_whisper.app:main.

pyproject's [project.gui-scripts] points `shuper-whisper` at
`shuper_whisper.app:main`, so this -- not main.py's main() -- is what every
installed copy and the PyInstaller build actually run. These tests pin the
behaviour that must not drift out of it again (see issue #11).
"""

import sys

import pytest

from shuper_whisper import app


def test_app_exposes_main():
    """The console-script target named in pyproject must actually exist."""
    assert callable(getattr(app, "main", None)), (
        "pyproject [project.gui-scripts] points shuper-whisper at "
        "shuper_whisper.app:main; that attribute must exist or every "
        "installed copy fails on launch"
    )


@pytest.fixture
def stub_main(mocker):
    """Neutralise everything main() touches, recording the call order."""
    calls = []
    mocker.patch.object(app, "_enable_dpi_awareness", side_effect=lambda: calls.append("dpi"))
    cfg = mocker.Mock(hotkey="ctrl+alt", model_size="base")

    def _load_config():
        calls.append("config")
        return cfg

    mocker.patch.object(app, "load_config", side_effect=_load_config)
    mocker.patch.object(app.multiprocessing, "freeze_support")
    return calls


def test_main_enables_dpi_before_config(mocker, stub_main):
    """DPI awareness must run before any config/UI work."""
    tray = mocker.patch("shuper_whisper.tray.TrayController")
    mocker.patch.object(sys, "argv", ["shuper-whisper"])

    app.main()

    assert stub_main[:2] == ["dpi", "config"]
    tray.return_value.run.assert_called_once()


def test_main_console_flag_runs_the_app_directly(mocker, stub_main):
    app_cls = mocker.patch.object(app, "ShuperWhisperApp")
    mocker.patch.object(sys, "argv", ["shuper-whisper", "--console"])

    app.main()

    app_cls.return_value.run.assert_called_once()


def test_main_list_devices_exits_without_starting_ui(mocker, stub_main):
    listing = mocker.patch.object(app, "list_devices")
    tray = mocker.patch("shuper_whisper.tray.TrayController")
    mocker.patch.object(sys, "argv", ["shuper-whisper", "--list-devices"])

    with pytest.raises(SystemExit):
        app.main()

    listing.assert_called_once()
    tray.assert_not_called()
    assert "config" not in stub_main


def test_main_calls_freeze_support_first(mocker, stub_main):
    """PyInstaller builds need freeze_support() before anything spawns."""
    freeze = mocker.patch.object(app.multiprocessing, "freeze_support")
    mocker.patch("shuper_whisper.tray.TrayController")
    mocker.patch.object(sys, "argv", ["shuper-whisper"])

    app.main()

    freeze.assert_called_once()


def test_setup_gpu_flag_runs_setup_window_and_exits(mocker, stub_main):
    run = mocker.patch("shuper_whisper.setup_window.run_setup_window", return_value=0)
    tray = mocker.patch("shuper_whisper.tray.TrayController")
    mocker.patch.object(sys, "argv", ["shuper-whisper", "--setup-gpu"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 0
    run.assert_called_once()
    tray.assert_not_called()
    assert "config" not in stub_main
