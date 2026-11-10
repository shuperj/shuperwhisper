import os
import wave

import numpy as np

from shuper_whisper import captures


def test_save_writes_audio_and_details(tmp_path):
    audio = np.full(16000, 0.25, np.float32)
    cid = captures.save(audio, {"mode": "live", "typed": "hello there"}, folder=str(tmp_path))
    assert len(captures.read_wav(str(tmp_path / f"{cid}.wav"))) == 16000
    meta = captures.load(cid, str(tmp_path))
    assert meta["typed"] == "hello there" and meta["mode"] == "live"
    assert meta["seconds"] == 1.0 and meta["flagged"] is False and meta["id"] == cid


def test_only_the_newest_are_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(captures, "KEEP", 3)
    ids = [captures.save(np.zeros(160, np.float32), {"n": i}, folder=str(tmp_path)) for i in range(5)]
    assert [m["n"] for m in captures.all_meta(str(tmp_path))] == [2, 3, 4]
    assert sorted(os.listdir(tmp_path)) == sorted(f"{i}{e}" for i in ids[2:] for e in (".wav", ".json"))


def test_flag_last_marks_the_newest(tmp_path):
    assert captures.flag_last(str(tmp_path)) is None
    captures.save(np.zeros(160, np.float32), {"n": 1}, folder=str(tmp_path))
    newest = captures.save(np.zeros(160, np.float32), {"n": 2}, folder=str(tmp_path))
    assert captures.flag_last(str(tmp_path)) == newest
    flags = {m["n"]: m["flagged"] for m in captures.all_meta(str(tmp_path))}
    assert flags == {1: False, 2: True}


def test_audio_is_saved_exactly(tmp_path):
    # faint background that 16-bit would round to silence survives
    audio = np.random.default_rng(0).normal(0, 1e-5, 16000).astype(np.float32)
    cid = captures.save(audio, {}, folder=str(tmp_path))
    assert np.array_equal(captures.read_wav(str(tmp_path / f"{cid}.wav")), audio)


def test_reads_16_bit_wavs_too(tmp_path):
    path = str(tmp_path / "old.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.array([0, 16384, -16384], np.int16).tobytes())
    assert captures.read_wav(path).tolist() == [0.0, 0.5, -0.5]
