"""Input-device discovery and resolution.

PortAudio lists each physical device once per Windows host API (MME,
DirectSound, WASAPI, WDM-KS) and renumbers devices whenever one appears or
disappears -- e.g. when Voicemeeter restarts. So config stores a device by name
and host API, and this module turns that reference into a current index.
"""

import threading
from dataclasses import asdict, dataclass, replace

import sounddevice as sd

HOSTAPI_PREFERENCE = ("Windows WASAPI", "MME", "Windows DirectSound")
HOSTAPI_LABELS = {"Windows WASAPI": "WASAPI", "MME": "MME", "Windows DirectSound": "DirectSound"}
_MME_NAME_LIMIT = 31  # MME truncates device names to 31 characters
_PSEUDO_DEVICES = ("Microsoft Sound Mapper - Input", "Primary Sound Capture Driver")
_RANK = {api: i for i, api in enumerate(HOSTAPI_PREFERENCE)}


class DeviceNotFoundError(RuntimeError):
    """The configured input device isn't connected right now."""


@dataclass(frozen=True)
class InputDevice:
    index: int
    name: str
    hostapi: str
    channels: int
    samplerate: float
    is_default: bool = False

    def ref(self) -> dict:
        return {"name": self.name, "hostapi": self.hostapi}

    def to_dict(self) -> dict:
        data = asdict(self)
        data["hostapi_label"] = HOSTAPI_LABELS.get(self.hostapi, self.hostapi)
        return data


# Re-scanning restarts PortAudio, which would free every open stream, so it
# only happens while none is open.
_streams_lock = threading.Lock()
_open_streams = 0


def stream_opened() -> None:
    global _open_streams
    with _streams_lock:
        _open_streams += 1


def stream_closed() -> None:
    global _open_streams
    with _streams_lock:
        _open_streams = max(0, _open_streams - 1)


def refresh() -> bool:
    """Re-scan devices (PortAudio otherwise caches the list from startup).

    Returns False, doing nothing, while any stream is open.
    """
    with _streams_lock:
        if _open_streams:
            return False
        sd._terminate()
        sd._initialize()
        return True


def _inputs(devices=None, hostapis=None) -> list[InputDevice]:
    devices = sd.query_devices() if devices is None else devices
    hostapis = sd.query_hostapis() if hostapis is None else hostapis
    found = []
    for index, d in enumerate(devices):
        api = hostapis[d["hostapi"]]["name"]
        if d["max_input_channels"] <= 0 or api not in _RANK or d["name"] in _PSEUDO_DEVICES:
            continue
        found.append(InputDevice(index, d["name"], api, int(d["max_input_channels"]),
                                 float(d["default_samplerate"])))
    return found


def default_input_index(devices=None, hostapis=None) -> int | None:
    """WASAPI's default input (its native-rate handling is the most reliable),
    else PortAudio's overall default."""
    hostapis = sd.query_hostapis() if hostapis is None else hostapis
    for api in hostapis:
        if api["name"] == "Windows WASAPI" and api.get("default_input_device", -1) >= 0:
            return api["default_input_device"]
    index = sd.default.device[0]
    return index if index is not None and index >= 0 else None


def list_input_devices(devices=None, hostapis=None) -> list[InputDevice]:
    """One entry per physical input, from the most preferred host API."""
    inputs = _inputs(devices, hostapis)
    default_index = default_input_index(devices, hostapis)
    default_key = next((d.name[:_MME_NAME_LIMIT] for d in inputs if d.index == default_index), None)

    groups: dict[str, list[InputDevice]] = {}
    for d in inputs:
        groups.setdefault(d.name[:_MME_NAME_LIMIT], []).append(d)

    result = []
    for key, group in groups.items():
        best = min(_RANK[d.hostapi] for d in group)
        for d in group:
            if _RANK[d.hostapi] == best:
                result.append(replace(d, is_default=(key == default_key)))
    return sorted(result, key=lambda d: d.name.lower())


def resolve(ref, devices=None, hostapis=None) -> int:
    """Current PortAudio index for a stored reference (None = system default)."""
    if ref is None:
        index = default_input_index(devices, hostapis)
        if index is None:
            raise DeviceNotFoundError("No microphone found")
        return index
    if isinstance(ref, int):
        return ref
    name, hostapi = ref["name"], ref.get("hostapi")
    inputs = _inputs(devices, hostapis)
    for matches in (
        [d for d in inputs if d.name == name and d.hostapi == hostapi],
        [d for d in inputs if d.name == name],
        [d for d in inputs if d.name[:_MME_NAME_LIMIT] == name[:_MME_NAME_LIMIT]],
    ):
        if matches:
            return min(matches, key=lambda d: _RANK[d.hostapi]).index
    raise DeviceNotFoundError(f"{name} isn't connected")


def migrate(value, devices=None, hostapis=None):
    """Turn a legacy int index into a reference; anything else passes through."""
    if not isinstance(value, int) or isinstance(value, bool):
        return value
    for d in _inputs(devices, hostapis):
        if d.index == value:
            return d.ref()
    devices = sd.query_devices() if devices is None else devices
    if 0 <= value < len(devices) and devices[value]["max_input_channels"] > 0:
        return {"name": devices[value]["name"], "hostapi": None}
    return None


def check(ref) -> str | None:
    """Try the device at its native rate. Returns an error message or None."""
    try:
        index = resolve(ref)
        info = sd.query_devices(index, "input")
        channels = max(1, min(int(info["max_input_channels"]), 2))
        try:
            sd.check_input_settings(device=index, channels=channels,
                                    samplerate=info["default_samplerate"], dtype="float32")
        except sd.PortAudioError:
            # Same fallback AudioRecorder uses: let WASAPI convert to 16 kHz.
            if "WASAPI" not in sd.query_hostapis(info["hostapi"])["name"]:
                raise
            sd.check_input_settings(device=index, channels=channels, samplerate=16000,
                                    dtype="float32",
                                    extra_settings=sd.WasapiSettings(auto_convert=True))
        return None
    except Exception as e:  # PortAudioError, DeviceNotFoundError, ValueError
        return str(e)
