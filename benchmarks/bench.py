"""Compare Whisper models for ShuperWhisper: memory, speed and dictation quality.

    python benchmarks/bench.py                      # default model list on the GPU
    python benchmarks/bench.py --models small.en base.en --device cpu
    python benchmarks/bench.py --compute float16    # another precision
    python benchmarks/bench.py --models large-v3-turbo --set synthetic --clips pause --tune JOIN_GAP=0.4

Each model runs in its own process (so its memory can be measured) through
the app's own code: Transcriber for type-on-stop, and StreamingSession +
LiveWriter for live typing, driven in simulated real time (the clock moves by
the poll interval plus however long each step really took, so a slow model
falls behind exactly as it would live, without the benchmark sleeping).

Results go to benchmarks/results/: a Markdown summary and the raw JSON.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import datetime
import json
import os
import statistics
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from corpus import SR, _read_wav, build_audio, own_audio, real_audio  # noqa: E402
from metrics import sentence_breaks, wer  # noqa: E402

DEFAULT_MODELS = ["large-v3-turbo", "distil-medium.en", "small.en", "small", "distil-small.en",
                  "base.en", "base", "tiny.en", "tiny"]
REAL = ("sermon", "libri_clean", "libri_other", "own")  # shown per set, not per clip
WORDS_ONLY = ("libri_clean", "libri_other")  # references without punctuation
HALLUCINATION = ("silence", "gap_clicks")     # scored as invented words, not WER
GROUPS = [  # (column, variants)
    ("Synthetic, clean", ("david", "zira", "zira_fast")),
    ("Synthetic, 10 dB noise", ("david_noisy",)),
    ("Synthetic, 3 dB noise", ("zira_noisy",)),
    ("Your voice", ("own",)),
    ("LibriSpeech clean", ("libri_clean",)),
    ("LibriSpeech other", ("libri_other",)),
    ("Sermons", ("sermon",)),
]
LATENCY_CLIP = os.path.join(HERE, ".audio", "long.david.wav")
TRAILING_SILENCE = 0.7  # the user presses stop about this long after the last word


# -- memory --------------------------------------------------------------------

def _gpu_used() -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, creationflags=0x08000000).stdout
    return int(out.strip().splitlines()[0])


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [
        (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                       "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                       "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]


def _ram() -> tuple[int, int]:
    """(working set, peak working set) of this process in MiB."""
    pmc = _PMC(cb=ctypes.sizeof(_PMC))
    ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                             ctypes.byref(pmc), pmc.cb)
    return pmc.WorkingSetSize >> 20, pmc.PeakWorkingSetSize >> 20


class _PeakGpu(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.peak = 0
        self._stop = threading.Event()

    def run(self):
        while not self._stop.wait(0.25):
            self.peak = max(self.peak, _gpu_used())

    def stop(self):
        self._stop.set()
        self.peak = max(self.peak, _gpu_used())


# -- one model -----------------------------------------------------------------

def _live(transcriber, audio, interval, speech_end):
    """Run a StreamingSession + LiveWriter over ``audio`` in simulated real time.
    ``lag``: seconds from ``speech_end`` until the field last changed."""
    from shuper_whisper.live_writer import LiveWriter
    from shuper_whisper.streaming import StreamingSession

    vt = [0.0]
    end = len(audio) / SR
    field = {"text": "", "backspaces": 0, "last_change": 0.0}
    step = {"vt": 0.0, "real": time.perf_counter()}  # where the current step started

    def send(text, backspaces=0):
        field["last_change"] = step["vt"] + time.perf_counter() - step["real"]
        field["backspaces"] += backspaces
        if backspaces:
            field["text"] = field["text"][:-backspaces]
        field["text"] += text

    class Monitor:
        user_input, healthy = False, True

        def __init__(self, **_kw):
            pass

        start = stop = clear = lambda self: None

    writer = LiveWriter(send=send, read_context=lambda: field["text"], field_id=lambda: (1, None),
                        monitor_factory=Monitor, wait_modifiers=lambda timeout=1.0: True)
    writer.begin()

    class Stop:
        flag = False

        def wait(self, timeout):
            vt[0] += timeout
            return self.flag or vt[0] >= end

        def set(self):
            self.flag = True

        def is_set(self):
            return self.flag or vt[0] >= end

    pos = [0]

    def read_audio():
        target = min(int(vt[0] * SR), len(audio))
        chunk = audio[pos[0]:target]
        pos[0] = max(pos[0], target)
        return chunk

    passes, finished = [], {}
    session = StreamingSession(
        transcriber, read_audio,
        on_hypothesis=lambda h: writer.update(h.stable_delta, h.tentative, final=h.final),
        on_finished=lambda error: finished.update(error=error, at=time.perf_counter()),
        on_auto_stop=lambda: None, interval=interval, clock=lambda: vt[0])
    session._stop = Stop()
    tick, decode = session._tick, transcriber.transcribe_words

    def timed_tick():
        step["vt"], step["real"] = vt[0], time.perf_counter()
        tick()
        vt[0] += time.perf_counter() - step["real"]
        step["vt"], step["real"] = vt[0], time.perf_counter()  # the final pass runs from here

    def timed_decode(*a, **k):
        t0 = time.perf_counter()
        try:
            return decode(*a, **k)
        finally:
            passes.append(time.perf_counter() - t0)

    session._tick = timed_tick
    transcriber.transcribe_words = timed_decode
    try:
        session._run()
    finally:
        transcriber.transcribe_words = decode
    writer.finish()
    return {"text": field["text"], "backspaces": field["backspaces"], "error": finished.get("error"),
            "lag": field["last_change"] - speech_end,
            "passes": len(passes), "pass_mean": statistics.mean(passes) if passes else 0.0}


def run_one(model: str, device: str, compute: str, items, skip_live: bool, tune: dict) -> dict:
    gpu = device == "cuda"
    base = _gpu_used() if gpu else 0
    import numpy as np

    from shuper_whisper import transcriber as tr
    from shuper_whisper.streaming import StreamingSession, silero_speech_spans
    from shuper_whisper.text_rules import clean, join
    from shuper_whisper import streaming
    for key, value in tune.items():  # "JOIN_GAP" or "LocalAgreement.HOLD_WORDS"
        cls, _, attr = key.rpartition(".")
        setattr(getattr(streaming, cls) if cls else StreamingSession, attr,
                int(value) if value == int(value) and attr.endswith("WORDS") else value)
    if gpu:
        tr.select_compute("auto")  # loads the CUDA runtime DLLs
    peak = _PeakGpu() if gpu else None
    if peak:
        peak.start()
    t0 = time.perf_counter()
    t = tr.Transcriber(model_size=model, language="en", live_typing="on", device=device,
                       compute_type=compute)
    t.load_model()
    result = {"model": model, "device": device, "compute": compute, "tune": tune,
              "load_s": time.perf_counter() - t0}
    if gpu:
        time.sleep(0.5)
        result["vram_loaded"] = _gpu_used() - base
    else:
        result["ram_loaded"] = _ram()[0]

    long_audio = _read_wav(LATENCY_CLIP)
    latency = {}
    for seconds in (3, 10, 25):
        clip = long_audio[:seconds * SR]
        t.transcribe_words(clip)
        runs = []
        for _ in range(5):
            t1 = time.perf_counter()
            t.transcribe_words(clip)
            runs.append(time.perf_counter() - t1)
        latency[str(seconds)] = statistics.median(runs)
    result["pass_latency"] = latency

    clips = []
    for clip_id, variant, path, expected in items:
        audio = _read_wav(path)
        row = {"clip": clip_id, "variant": variant, "expected": expected, "seconds": len(audio) / SR}
        t1 = time.perf_counter()
        row["batch"] = {"text": join(clean(t.transcribe(audio)), ""), "seconds": time.perf_counter() - t1}
        if not skip_live:
            padded = np.concatenate([audio, np.zeros(int(TRAILING_SILENCE * SR), np.float32)])
            spans = silero_speech_spans(audio)
            speech_end = max(0.0, spans[-1][1] / SR - 0.1) if spans else 0.0  # VAD pads 0.1 s
            row["live"] = _live(t, padded, 0.4 if gpu else 1.0, speech_end)
        clips.append(row)
        score = wer(expected, row["live"]["text"] if "live" in row else row["batch"]["text"])
        print(f"  {model:18} {clip_id:34} {variant:11} {score[0]}/{score[1]}", flush=True)
    result["clips"] = clips
    if gpu:
        peak.stop()
        result["vram_peak"] = peak.peak - base
    else:
        result["ram_peak"] = _ram()[1]
    return result


# -- summary -------------------------------------------------------------------
# Scores are computed here from the stored texts, so a scoring change applies
# to old runs too (--summarise).

def _score(rows):
    for r in rows:
        for mode in ("batch", "live"):
            if mode in r:
                r[mode]["wer"] = wer(r["expected"], r[mode]["text"])
                r[mode]["breaks"] = sentence_breaks(r["expected"], r[mode]["text"])
    return rows


def _rate(rows, mode, variants):
    hits = [r for r in rows if r["variant"] in variants and mode in r and r["clip"] not in HALLUCINATION]
    words = sum(r[mode]["wer"][1] for r in hits)
    return 100 * sum(r[mode]["wer"][0] for r in hits) / words if words else None


def _breaks(rows, variants):
    hits = [r for r in rows if r["variant"] in variants and "live" in r and r["clip"] != "silence"]
    if not hits:
        return None
    return sum(r["live"]["breaks"][0] for r in hits), sum(r["live"]["breaks"][1] for r in hits)


def _pct(value):
    return "-" if value is None else f"{value:.1f}%"


def summarise(results: list[dict]) -> str:
    gpu = results[0]["device"] == "cuda"
    for res in results:
        _score(res["clips"])
    present = {r["variant"] for res in results for r in res["clips"]}
    groups = [(name, vs) for name, vs in GROUPS if present & set(vs)]
    live = any("live" in r for res in results for r in res["clips"])
    out = []

    # 1. memory and speed
    mem = "VRAM loaded / peak" if gpu else "RAM loaded / peak"
    head = ["Model", mem, "Load", "One live pass, 3 s / 10 s / 25 s of audio"]
    if live:
        head += ["Typing lag, median / worst", "Backspaces per 100 words"]
    out += ["## Memory and speed", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for res in results:
        m = (f"{res['vram_loaded']} / {res['vram_peak']} MB" if gpu
             else f"{res['ram_loaded']} / {res['ram_peak']} MB")
        cells = [f"`{res['model']}`", m, f"{res['load_s']:.1f} s",
                 " / ".join(f"{1000 * res['pass_latency'][s]:.0f}" for s in ("3", "10", "25")) + " ms"]
        if live:
            rows = [r for r in res["clips"] if "live" in r and r["clip"] != "silence"]
            lags = [r["live"]["lag"] for r in rows]
            words = sum(r["live"]["wer"][1] for r in rows)
            cells += [f"{statistics.median(lags):.1f} / {max(lags):.1f} s",
                      f"{100 * sum(r['live']['backspaces'] for r in rows) / max(words, 1):.0f}"]
        out.append("| " + " | ".join(cells) + " |")

    # 2. word error rate
    out += ["", "## Word error rate", "",
            "Type-on-stop -> live typing. Lower is better.", "",
            "| Model | " + " | ".join(name for name, _ in groups) + " |", "|---|" + "---|" * len(groups)]
    for res in results:
        cells = []
        for _name, vs in groups:
            b, l = _rate(res["clips"], "batch", vs), _rate(res["clips"], "live", vs)
            cells.append(_pct(b) + (f" -> {_pct(l)}" if live else ""))
        out.append(f"| `{res['model']}` | " + " | ".join(cells) + " |")

    # 3. punctuation and invented text
    if live:
        punct = [(name, vs) for name, vs in groups if not set(vs) & set(WORDS_ONLY)]
        out += ["", "## Sentence breaks and invented text (live typing)", "",
                "False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). "
                "Invented: words typed for the silence clip plus extra words around the quiet stretch.", "",
                "| Model | " + " | ".join(name for name, _ in punct) + " | Invented words |",
                "|---|" + "---|" * (len(punct) + 1)]
        for res in results:
            rows = res["clips"]
            invented = sum(len(r[k]["text"].split()) for r in rows if r["clip"] == "silence"
                           for k in ("batch", "live") if k in r)
            invented += sum(max(0, len(r["live"]["text"].split()) - len(r["expected"].split()))
                            for r in rows if r["clip"] == "gap_clicks" and "live" in r)
            cells = []
            for _name, vs in punct:
                b = _breaks(rows, vs)
                cells.append("-" if b is None else f"{b[0]} / {b[1]}")
            out.append(f"| `{res['model']}` | " + " | ".join(cells) + f" | {invented} |")

        # 4. per clip
        clip_ids = list(dict.fromkeys(r["clip"] if r["variant"] not in REAL else r["variant"]
                                      for r in results[0]["clips"]))
        out += ["", "## Live word error rate by clip", "",
                "Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.", "",
                "| Clip | " + " | ".join(f"`{r['model']}`" for r in results) + " |",
                "|---|" + "---|" * len(results)]
        for cid in clip_ids:
            cells = []
            for res in results:
                rows = [r for r in res["clips"] if "live" in r and
                        (r["variant"] == cid if cid in REAL else r["clip"] == cid and r["variant"] not in REAL)]
                e, n = sum(r["live"]["wer"][0] for r in rows), sum(r["live"]["wer"][1] for r in rows)
                f, m = (sum(r["live"]["breaks"][i] for r in rows) for i in (0, 1))
                cell = f"{100 * e / n:.0f}%" if n else f"{e} words"
                cells.append(cell + (f" ({f}/{m})" if (f or m) and cid not in WORDS_ONLY else ""))
            out.append(f"| {cid} | " + " | ".join(cells) + " |")
        sermons = sorted({r["clip"].rsplit("-", 1)[0] for r in results[0]["clips"] if r["variant"] == "sermon"})
        if sermons:
            out += ["", "## Live word error rate by sermon", "",
                    "| Sermon | " + " | ".join(f"`{r['model']}`" for r in results) + " |",
                    "|---|" + "---|" * len(results)]
            for sermon in sermons:
                cells = []
                for res in results:
                    rows = [r for r in res["clips"] if "live" in r and r["clip"].rsplit("-", 1)[0] == sermon]
                    e, n = sum(r["live"]["wer"][0] for r in rows), sum(r["live"]["wer"][1] for r in rows)
                    cells.append(f"{100 * e / n:.0f}%" if n else "-")
                out.append(f"| {sermon.removeprefix('sermon-')} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--compute", default=None, help="default: int8_float16 on GPU, int8 on CPU")
    parser.add_argument("--set", default="all", choices=["all", "synthetic", "real", "own"],
                        help="real = the asr-shootout clips (extract_real.py); own = your voice (record.py)")
    parser.add_argument("--clips", nargs="+", help="only clips whose id starts with one of these")
    parser.add_argument("--variants", nargs="+", help="only these variants (david, sermon, libri_other...)")
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--tune", nargs="+", default=[], metavar="NAME=VALUE",
                        help="override streaming settings, e.g. JOIN_GAP=0.4 or LocalAgreement.HOLD_WORDS=1")
    parser.add_argument("--label", default="", help="added to the results file name")
    parser.add_argument("--summarise", metavar="RAW_DIR",
                        help="rewrite the summary from a finished run's raw JSON")
    parser.add_argument("--child", help=argparse.SUPPRESS)
    parser.add_argument("--out", help=argparse.SUPPRESS)
    args = parser.parse_args()
    compute = args.compute or ("int8_float16" if args.device == "cuda" else "int8")
    tune = {k: float(v) for k, v in (t.split("=", 1) for t in args.tune)}

    if args.summarise:
        files = sorted(f for f in os.listdir(args.summarise) if f.endswith(".json"))
        raw = {f[:-5]: json.load(open(os.path.join(args.summarise, f), encoding="utf-8")) for f in files}
        order = [m for m in args.models if m in raw] + [m for m in raw if m not in args.models]
        print(summarise([raw[m] for m in order]))
        return

    cache = os.path.join(HERE, ".audio")
    items = []
    if args.set in ("all", "synthetic"):
        items += build_audio(cache)
    if args.set in ("all", "real"):
        items += real_audio(cache)
    if args.set in ("all", "own"):
        items += own_audio(cache)
    if args.clips:
        items = [i for i in items if i[0].startswith(tuple(args.clips))]
    if args.variants:
        items = [i for i in items if i[1] in args.variants]

    if args.child:
        build_audio(cache)  # the latency clip
        result = run_one(args.child, args.device, compute, items, args.skip_live, tune)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        return

    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    name = f"{stamp}-{args.device}-{compute}" + (f"-{args.label}" if args.label else "")
    raw_dir = os.path.join(HERE, "results", "raw", name)
    os.makedirs(raw_dir, exist_ok=True)
    results = []
    for model in args.models:
        out = os.path.join(raw_dir, f"{model}.json")
        print(f"== {model}", flush=True)
        cmd = [sys.executable, __file__, "--child", model, "--out", out, "--device", args.device,
               "--compute", compute, "--set", args.set]
        for flag in ("clips", "variants", "tune"):
            if getattr(args, flag):
                cmd += [f"--{flag}"] + list(getattr(args, flag))
        cmd += ["--skip-live"] if args.skip_live else []
        if subprocess.run(cmd).returncode != 0 or not os.path.exists(out):
            print(f"   {model} failed; skipped", flush=True)
            continue
        with open(out, encoding="utf-8") as f:
            results.append(json.load(f))
    gpu_name = ""
    if args.device == "cuda":
        gpu_name = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                  capture_output=True, text=True).stdout.strip()
    title = f"# Model benchmark {name}: {args.device} {compute} {gpu_name}".rstrip()
    detail = f"Command: `python benchmarks/bench.py {' '.join(sys.argv[1:])}`"
    summary = f"{title}\n\n{detail}\n\n{summarise(results)}"
    path = os.path.join(HERE, "results", f"{name}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(summary)
    print(f"\nWritten to {path}")


if __name__ == "__main__":
    main()
