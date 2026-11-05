"""Saved dictations, for testing (the tray's "Save dictations for testing",
which keeps every one, and "Last dictation was wrong", which saves the last).

Each dictation is kept as <id>.wav (16 kHz mono) plus <id>.json: how it ran
(live or type-on-stop, device, model, dictionary), what was typed, and the
hypotheses in order. Flagged ones are the ones that came out wrong;
benchmarks/captures.py turns flagged ones into benchmark clips. Only the
newest KEEP are kept. Nothing leaves the machine.
"""

import datetime
import json
import os
import wave
from typing import Optional

import numpy as np

SAMPLE_RATE = 16000
KEEP = 50


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
    with wave.open(os.path.join(folder, f"{cid}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
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
