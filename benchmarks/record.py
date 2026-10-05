"""Record the benchmark sentences in your own voice, through the microphone
ShuperWhisper is set to use. bench.py then scores every model on them too
(variant "own"), which says far more than synthetic speech does.

    python benchmarks/record.py            # all sentences
    python benchmarks/record.py names long # re-record some

Read each sentence naturally. Where it says [pause], stop for a second or so,
as if thinking. Press Enter to start, and Enter again when you're done.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from corpus import CLIPS, _write_wav  # noqa: E402

from shuper_whisper.audio import AudioRecorder  # noqa: E402
from shuper_whisper.config import load_config  # noqa: E402

OWN_DIR = os.path.join(HERE, ".audio", "own")


def _script(ssml: str) -> str:
    return re.sub(r"\s*<break[^>]*/>\s*", " [pause] ", ssml).strip()


def main():
    wanted = set(sys.argv[1:])
    os.makedirs(OWN_DIR, exist_ok=True)
    recorder = AudioRecorder(load_config().input_device)
    clips = [c for c in CLIPS if not wanted or c.id in wanted]
    for n, clip in enumerate(clips, 1):
        print(f"\n[{n}/{len(clips)}] {clip.id}\n\n    {_script(clip.ssml)}\n")
        input("Enter to start recording... ")
        recorder.start_recording()
        input("Recording. Enter when done. ")
        audio = recorder.stop_recording()
        if audio is None or not len(audio):
            print("Nothing recorded; check the microphone in ShuperWhisper's settings.")
            continue
        _write_wav(os.path.join(OWN_DIR, f"{clip.id}.wav"), audio)
        print(f"Saved ({len(audio) / 16000:.1f} s).")
    print(f"\nDone. Recordings are in {OWN_DIR}; run benchmarks/bench.py to score them.")


if __name__ == "__main__":
    main()
