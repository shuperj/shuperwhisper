import pytest

from shuper_whisper import audio_devices


@pytest.fixture(autouse=True)
def _reset_open_stream_count():
    """Tests open fake streams without always closing them; don't let the
    module-level counter leak between tests."""
    audio_devices._open_streams = 0
    yield
    audio_devices._open_streams = 0


def pytest_addoption(parser):
    parser.addoption("--run-model", action="store_true",
                     help="run tests that load a real Whisper model (tests/test_quality.py)")
    parser.addoption("--update-budget", action="store_true",
                     help="with --run-model: write today's invented-word counts as the budget")


def pytest_configure(config):
    config.addinivalue_line("markers", "model: loads a real Whisper model; needs --run-model")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-model"):
        return
    skip = pytest.mark.skip(reason="loads a real model: run with --run-model")
    for item in items:
        if "model" in item.keywords:
            item.add_marker(skip)
