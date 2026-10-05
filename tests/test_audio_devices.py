"""Tests for device listing, de-duplication, resolution and migration."""

import pytest

from shuper_whisper import audio_devices as ad

HOSTAPIS = [
    {"name": "MME", "default_input_device": 1},
    {"name": "Windows DirectSound", "default_input_device": 4},
    {"name": "Windows WASAPI", "default_input_device": 7},
    {"name": "Windows WDM-KS", "default_input_device": -1},
]


def dev(name, hostapi, ins=2, rate=48000.0):
    return {"name": name, "hostapi": hostapi, "max_input_channels": ins,
            "default_samplerate": rate}


B1 = "Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO)"
MIC = "Microphone (Realtek(R) Audio)"
DEVICES = [
    dev("Microsoft Sound Mapper - Input", 0),          # 0 pseudo
    dev(MIC, 0, rate=44100.0),                         # 1 MME
    dev(B1[:31], 0, rate=44100.0),                     # 2 MME, truncated
    dev("Speakers (Realtek(R) Audio)", 0, ins=0),      # 3 output only
    dev(MIC, 1),                                       # 4 DirectSound
    dev(B1, 1),                                        # 5 DirectSound
    dev("Primary Sound Capture Driver", 1),            # 6 pseudo
    dev(MIC, 2),                                       # 7 WASAPI (default)
    dev(B1, 2),                                        # 8 WASAPI
    dev("Voicemeeter Point 1", 3),                     # 9 WDM-KS
    dev("Old USB Mic", 0, rate=44100.0),               # 10 MME only
]


def listing():
    return ad.list_input_devices(DEVICES, HOSTAPIS)


class TestList:
    def test_one_entry_per_device_preferring_wasapi(self):
        got = {(d.name, d.hostapi) for d in listing()}
        assert got == {(MIC, "Windows WASAPI"), (B1, "Windows WASAPI"), ("Old USB Mic", "MME")}

    def test_drops_wdmks_and_pseudo_devices(self):
        names = [d.name for d in listing()]
        assert "Voicemeeter Point 1" not in names
        assert "Microsoft Sound Mapper - Input" not in names

    def test_default_marked(self):
        defaults = [d.name for d in listing() if d.is_default]
        assert defaults == [MIC]

    def test_to_dict_has_label(self):
        d = next(d for d in listing() if d.name == B1).to_dict()
        assert d["hostapi_label"] == "WASAPI"
        assert d["index"] == 8


class TestResolve:
    def test_none_is_wasapi_default(self):
        assert ad.resolve(None, DEVICES, HOSTAPIS) == 7

    def test_exact_ref(self):
        assert ad.resolve({"name": B1, "hostapi": "Windows DirectSound"}, DEVICES, HOSTAPIS) == 5

    def test_name_only_prefers_wasapi(self):
        assert ad.resolve({"name": B1, "hostapi": None}, DEVICES, HOSTAPIS) == 8

    def test_hostapi_gone_falls_back_to_same_name(self):
        assert ad.resolve({"name": "Old USB Mic", "hostapi": "Windows WASAPI"}, DEVICES, HOSTAPIS) == 10

    def test_truncated_mme_name_matches(self):
        assert ad.resolve({"name": B1[:31], "hostapi": "MME"}, DEVICES, HOSTAPIS) == 2

    def test_missing_device_raises(self):
        with pytest.raises(ad.DeviceNotFoundError, match="Ghost Mic"):
            ad.resolve({"name": "Ghost Mic", "hostapi": None}, DEVICES, HOSTAPIS)


class TestMigrate:
    def test_int_becomes_ref(self):
        assert ad.migrate(8, DEVICES, HOSTAPIS) == {"name": B1, "hostapi": "Windows WASAPI"}

    def test_wdmks_index_becomes_name_only(self):
        assert ad.migrate(9, DEVICES, HOSTAPIS) == {"name": "Voicemeeter Point 1", "hostapi": None}

    def test_out_of_range_becomes_default(self):
        assert ad.migrate(99, DEVICES, HOSTAPIS) is None

    def test_non_int_passes_through(self):
        ref = {"name": B1, "hostapi": None}
        assert ad.migrate(ref, DEVICES, HOSTAPIS) is ref
        assert ad.migrate(None, DEVICES, HOSTAPIS) is None
