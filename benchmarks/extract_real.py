"""Cut real-speech benchmark clips out of the asr-shootout corpus.

Run where that corpus's audio lives (the sermons CT, ~/apps/asr-shootout):

    python3 extract_real.py <corpus dir> <out dir>

Writes <out dir>/<id>.wav (16 kHz mono) and <out dir>/manifest.json with each
clip's reference text. Needs ffmpeg. bench.py picks the folder up from
benchmarks/.audio/real/.

- Sermons: only answer keys a human verified; segments of 12-25 s inside the
  gold stretch, cut at sentence ends (the key's word times run back to back,
  so there are few gaps to cut at), speech regions only (no music).
  The keys are punctuated, so these also score sentence breaks.
- LibriSpeech: single utterances of 5-20 s, half test-clean, half test-other.
  Its references have no punctuation, so these score words only.

The sermon audio is for internal testing only: never commit or share it.
"""

import json
import os
import re
import subprocess
import sys

SERMON_SEGMENTS = 4
LIBRI_PER_SPLIT = 12


def _cut(src, start, end, dest):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                    "-i", src, "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", dest], check=True)


def _clean_text(words):
    text = " ".join(w["text"] for w in words)
    text = re.sub(r"\[[^\]]*\]", " ", text)  # [music], [inaudible] tags
    return " ".join(text.split())


def _speech_only(regions, start, end):
    return all(r["kind"] == "speech" for r in regions if r["start"] < end and r["end"] > start)


def sermons(corpus, out):
    clips = []
    for name in sorted(os.listdir(os.path.join(corpus, "sermons"))):
        folder = os.path.join(corpus, "sermons", name)
        ref = json.load(open(os.path.join(folder, "reference.json"), encoding="utf-8"))
        if ref.get("verified") != "human" or not ref.get("stretches"):
            continue
        stretch = ref["stretches"][0]
        words = [w for w in ref["words"] if stretch["start"] <= w["start"] and w["end"] <= stretch["end"]]
        # candidate cut points: the start of a sentence
        cuts = [i for i in range(1, len(words))
                if words[i - 1]["text"].rstrip("\"')").endswith((".", "?", "!"))]
        found, step = [], max(1, len(cuts) // (SERMON_SEGMENTS * 3))
        for a in cuts[::step]:
            seg_start = words[a]["start"]
            ends = [b for b in cuts if b > a and 12 <= words[b - 1]["end"] - seg_start <= 25]
            if not ends:
                continue
            b = ends[-1]
            seg = words[a:b]
            lo, hi = seg_start - 0.15, seg[-1]["end"] + 0.15
            if not _speech_only(ref["regions"], lo, hi) or len(seg) < 15:
                continue
            if found and lo < found[-1][1]:
                continue
            found.append((lo, hi, seg))
        # spread the picks across the stretch
        picks = found[:: max(1, len(found) // SERMON_SEGMENTS)][:SERMON_SEGMENTS]
        for n, (lo, hi, seg) in enumerate(picks):
            cid = f"sermon-{name}-{n}"
            _cut(os.path.join(folder, "audio.ogg"), lo, hi, os.path.join(out, f"{cid}.wav"))
            clips.append({"id": cid, "set": "sermon", "expected": _clean_text(seg),
                          "seconds": round(hi - lo, 2), "source": name})
    return clips


def librispeech(corpus, out):
    clips = []
    root = os.path.join(corpus, "librispeech")
    for split in ("test-clean", "test-other"):
        picked = 0
        for name in sorted(os.listdir(root)):
            if not name.startswith(split) or picked >= LIBRI_PER_SPLIT:
                continue
            ref = json.load(open(os.path.join(root, name, "reference.json"), encoding="utf-8"))
            utterances = {}
            for w in ref["words"]:  # word times are the utterance's span
                utterances.setdefault((w["start"], w["end"]), []).append(w["text"])
            good = [(s, e, ws) for (s, e), ws in utterances.items() if 5 <= e - s <= 20]
            if not good:
                continue
            s, e, ws = good[len(good) // 2]  # one per chapter, so one per speaker
            cid = f"libri-{name}"
            _cut(os.path.join(root, name, "audio.ogg"), s, e, os.path.join(out, f"{cid}.wav"))
            clips.append({"id": cid, "set": "libri_" + split.split("-")[1], "expected": " ".join(ws).lower(),
                          "seconds": round(e - s, 2), "source": name})
            picked += 1
    return clips


def main():
    corpus, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    clips = sermons(corpus, out) + librispeech(corpus, out)
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(clips, f, indent=1)
    by_set = {}
    for c in clips:
        by_set.setdefault(c["set"], []).append(c["seconds"])
    for name, secs in by_set.items():
        print(f"{name}: {len(secs)} clips, {sum(secs) / 60:.1f} min")


if __name__ == "__main__":
    main()
