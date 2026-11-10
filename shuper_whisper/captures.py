"""Saved dictations, for testing (the tray's "Save dictations for testing",
which keeps every one, and "Last dictation was wrong", which saves the last).

Each dictation is kept as <id>.wav (16 kHz mono, 32-bit float: exactly what
the model heard, faint background included, which 16-bit rounded to silence)
plus <id>.json: how it ran (live or type-on-stop, device, model, dictionary),
what was typed, the hypotheses in order, and every decode's input and output.
Flagged ones are the ones that came out wrong; benchmarks/label_captures.py
turns them into benchmark clips. Only the
newest KEEP are kept. Nothing leaves the machine.
"""

import datetime
import json
import os
import struct
from typing import Optional

import numpy as np

SAMPLE_RATE = 16000
KEEP = 50


def write_wav(path: str, audio: np.ndarray) -> None:
    """16 kHz mono 32-bit float WAV (format 3), the samples as the model got them."""
    data = np.asarray(audio, dtype="<f4").tobytes()
    fmt = struct.pack("<HHIIHHH", 3, 1, SAMPLE_RATE, SAMPLE_RATE * 4, 4, 32, 0)
    fact = struct.pack("<I", len(data) // 4)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(fact) + 8 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"fact" + struct.pack("<I", len(fact)) + fact)
        f.write(b"data" + struct.pack("<I", len(data)) + data)


def read_wav(path: str) -> np.ndarray:
    """A mono WAV as float32: 32-bit float (saved dictations) or 16-bit PCM."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError(f"not a WAV file: {path}")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(raw):
        tag, size = raw[pos:pos + 4], struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if tag == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif tag == b"data":
            data = body
        pos += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError(f"no audio in {path}")
    kind, channels, _rate, _bps, _align, bits = fmt
    if kind == 3 and bits == 32:
        samples = np.frombuffer(data, "<f4")
    elif kind == 1 and bits == 16:
        samples = np.frombuffer(data, "<i2").astype(np.float32) / 32768
    else:
        raise ValueError(f"unsupported WAV ({kind}, {bits}-bit): {path}")
    return samples.reshape(-1, channels).mean(axis=1).astype(np.float32) if channels > 1         else samples.astype(np.float32)


def capture_dir() -> str:
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(base, "ShuperWhisper", "captures")


def _ids(folder: str) -> list[str]:
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return sorted(n[:-5] for n in names if n.endswith(".json"))


def save(audio: np.ndarray, meta: dict, folder: Optional[str] = None) -> str:
    """Write one dictation; returns its id. Older ones beyond KEEP go."""
    folder = folder or capture_dir()
    os.makedirs(folder, exist_ok=True)
    now = datetime.datetime.now()
    cid = now.strftime("%Y-%m-%d-%H%M%S-") + f"{now.microsecond // 1000:03d}"
    n = 0
    while os.path.exists(os.path.join(folder, f"{cid}.json")):  # same millisecond
        n += 1
        cid = cid[:23] + f"-{n}"
    write_wav(os.path.join(folder, f"{cid}.wav"), audio)
    meta = {"id": cid, "time": now.isoformat(timespec="seconds"),
            "seconds": round(len(audio) / SAMPLE_RATE, 2), "flagged": False, **meta}
    with open(os.path.join(folder, f"{cid}.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    prune(folder)
    return cid


def prune(folder: Optional[str] = None, keep: Optional[int] = None) -> None:
    """Delete all but the newest ``keep`` (KEEP) dictations. Flagged ones
    count too: label them (benchmarks/captures.py) to keep them for good."""
    folder = folder or capture_dir()
    keep = KEEP if keep is None else keep
    for cid in _ids(folder)[:-keep] if keep else _ids(folder):
        for ext in (".wav", ".json"):
            try:
                os.remove(os.path.join(folder, cid + ext))
            except OSError:
                pass


def last(folder: Optional[str] = None) -> Optional[str]:
    ids = _ids(folder or capture_dir())
    return ids[-1] if ids else None


def load(cid: str, folder: Optional[str] = None) -> dict:
    with open(os.path.join(folder or capture_dir(), f"{cid}.json"), encoding="utf-8") as f:
        return json.load(f)


def set_flag(cid: str, flagged: bool = True, folder: Optional[str] = None) -> None:
    folder = folder or capture_dir()
    meta = load(cid, folder)
    meta["flagged"] = flagged
    with open(os.path.join(folder, f"{cid}.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)


def flag_last(folder: Optional[str] = None) -> Optional[str]:
    """Mark the newest dictation as typed wrong; returns its id."""
    cid = last(folder)
    if cid:
        set_flag(cid, True, folder)
    return cid


def all_meta(folder: Optional[str] = None) -> list[dict]:
    folder = folder or capture_dir()
    out = []
    for cid in _ids(folder):
        try:
            out.append(load(cid, folder))
        except (OSError, json.JSONDecodeError):
            pass
    return out
