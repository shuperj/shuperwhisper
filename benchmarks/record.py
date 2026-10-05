"""Record the benchmark script (own_script.py) in your own voice, through the
microphone ShuperWhisper is set to use. bench.py then scores every model on
it as "Your voice", which says far more than synthetic speech does.

    python benchmarks/record.py               # the passages not recorded yet
    python benchmarks/record.py --all         # start over
    python benchmarks/record.py own-07 own-12 # redo some

About four minutes of reading. Read each passage naturally, at your usual
pace. Where it says [pause], stop for a second or so, as if thinking.
Press Enter to start, Enter again when you're done, then Enter to keep it
or r to redo it.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from corpus import SR, _write_wav  # noqa: E402
from own_script import OWN_SCRIPT  # noqa: E402

from shuper_whisper.audio import AudioRecorder  # noqa: E402
from shuper_whisper.config import load_config  # noqa: E402

OWN_DIR = os.path.join(HERE, ".audio", "own")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    start_over = "--all" in sys.argv
    os.makedirs(OWN_DIR, exist_ok=True)

    def path(cid):
        return os.path.join(OWN_DIR, f"{cid}.wav")

    if args:
        todo = [(c, t) for c, t in OWN_SCRIPT if c.startswith(tuple(args))]
    else:
        todo = [(c, t) for c, t in OWN_SCRIPT if start_over or not os.path.exists(path(c))]
    if not todo:
        print("Everything is recorded. --all starts over; name passages to redo them.")
        return

    recorder = AudioRecorder(load_config().input_device)
    print(f"{len(todo)} passages. Ctrl+C stops; what's recorded so far is kept.")
    for n, (cid, text) in enumerate(todo, 1):
        while True:
            print(f"\n[{n}/{len(todo)}] {cid}\n\n    {text}\n")
            input("Enter to start... ")
            recorder.start_recording()
            input("Recording. Enter when done. ")
            audio = recorder.stop_recording()
            if audio is None or not len(audio):
                print("Nothing was recorded: check the microphone in ShuperWhisper's settings.")
                continue
            if input(f"{len(audio) / SR:.1f} s. Enter to keep, r to redo: ").strip().lower() != "r":
                _write_wav(path(cid), audio)
                break
    done = sum(os.path.exists(path(c)) for c, _ in OWN_SCRIPT)
    print(f"\n{done}/{len(OWN_SCRIPT)} passages recorded in {OWN_DIR}.")
    print("Score them: python benchmarks/bench.py --set own")


if __name__ == "__main__":
    main()
