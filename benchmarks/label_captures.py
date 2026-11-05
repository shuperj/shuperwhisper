"""Turn dictations that typed the wrong thing into benchmark clips.

With "Save dictations for testing" on (tray), ShuperWhisper keeps your recent
dictations; "Last dictation was wrong" flags the newest. This script shows
each flagged one with what was typed. You type what you actually said, and it
becomes a clip in benchmarks/.audio/captured/ (gitignored, like your own
voice), which `bench.py --set captured` and `pytest --run-model` replay.

    python benchmarks/label_captures.py           # flagged ones not labelled yet
    python benchmarks/label_captures.py --all     # any saved dictation
    python benchmarks/label_captures.py --list    # just list them
"""

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from shuper_whisper import captures  # noqa: E402

OUT = os.path.join(HERE, ".audio", "captured")
MANIFEST = os.path.join(OUT, "manifest.json")


def _manifest() -> list[dict]:
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def _play(path: str) -> None:
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception as e:
        print(f"  (can't play it here: {e})")


def main():
    everything, listing = "--all" in sys.argv, "--list" in sys.argv
    folder = captures.capture_dir()
    labelled = {c["id"] for c in _manifest()}
    todo = [m for m in captures.all_meta(folder)
            if m["id"] not in labelled and (everything or m.get("flagged"))]
    if not todo:
        print(f"Nothing to label in {folder}. Flag a dictation with \"Last dictation was wrong\" "
              "in the tray (with \"Save dictations for testing\" on), or use --all.")
        return
    for m in todo:
        print(f"{m['id']}  {m.get('mode')} on {m.get('device')} ({m.get('model')}), {m['seconds']} s"
              f"{'  FLAGGED' if m.get('flagged') else ''}\n    typed: {m.get('typed') or '(nothing)'}")
    if listing:
        return
    os.makedirs(OUT, exist_ok=True)
    manifest = _manifest()
    print("\nFor each: type what you actually said. p plays it, Enter skips, q stops.")
    for m in todo:
        wav = os.path.join(folder, f"{m['id']}.wav")
        print(f"\n{m['id']} ({m['seconds']} s)\n    typed: {m.get('typed') or '(nothing)'}")
        while True:
            said = input("    said:  ").strip()
            if said.lower() == "p":
                _play(wav)
                continue
            break
        if said.lower() == "q":
            break
        if not said:
            continue
        shutil.copyfile(wav, os.path.join(OUT, f"{m['id']}.wav"))
        manifest.append({"id": m["id"], "expected": said, "typed": m.get("typed", ""),
                         "mode": m.get("mode"), "device": m.get("device"), "model": m.get("model"),
                         "hotwords": m.get("hotwords"), "replacements": m.get("replacements", []),
                         "time": m.get("time")})
        with open(MANIFEST, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1)
        print(f"    kept as a test clip ({len(manifest)} in total)")
    print("\nReplay them: python benchmarks/bench.py --set captured --models base.en --repeat 3 --pace fixed")


if __name__ == "__main__":
    main()
