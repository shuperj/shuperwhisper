import pytest

from shuper_whisper import audio_devices


@pytest.fixture(autouse=True)
def _reset_open_stream_count():
    """Tests open fake streams without always closing them; don't let the
    module-level counter leak between tests."""
    audio_devices._open_streams = 0
    yield
    audio_devices._open_streams = 0
