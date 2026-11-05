"""Invented words on real speech, with the real model (opt-in).

    pytest tests/test_quality.py --run-model                  # check against the budget
    pytest tests/test_quality.py --run-model --update-budget  # record today's numbers

Runs base.en over your own recordings (benchmarks/.audio/own, record.py)
and your labelled dictations (benchmarks/.audio/captured, label_captures.py)
the way the app does: type-on-stop on the processor, and live typing on the
GPU at normal pace and as if a game shared the card. Live typing runs three
fixed-pace seeds, so a run replays the same way on a busy machine. Fails if
more words are typed that weren't said than benchmarks/quality_budget.json
allows. Skipped without --run-model, the recordings, or (for live) a GPU.
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "benchmarks")
AUDIO = os.path.join(BENCH, ".audio")
BUDGET = os.path.join(BENCH, "quality_budget.json")
MODEL = "base.en"
SEEDS = 3

pytestmark = pytest.mark.model

# A fixed dictionary like the one the app is used with, so the test doesn't
# depend on this machine's: words with and without phonetic hints.
DICTIONARY = [("Mackinaw", ""), ("claude.md", ""), ("shuper", ""), ("onebynine", "one by nine"),
              ("gitea", "gitty")]

SCENARIOS = {
    # name: (device, live, slow)
    "cpu-stop": ("cpu", False, 1.0),
    "gpu-live": ("cuda", True, 1.0),
    "gpu-live-busy": ("cuda", True, 2.5),
}


@pytest.fixture(scope="module")
def bench():
    pytest.importorskip("regex")
    pytest.importorskip("more_itertools")
    sys.path[:0] = [BENCH, ROOT]
    import bench as bench_module
    return bench_module


@pytest.fixture(scope="module")
def dictionary(tmp_path_factory):
    from shuper_whisper.dictionary import WordDictionary
    d = WordDictionary(path=str(tmp_path_factory.mktemp("dict") / "dictionary.json"))
    for word, phonetic in DICTIONARY:
        d.add(word, phonetic)
    return d.get_hotwords(), d.get_replacements()


def _items():
    from corpus import captured_audio, own_audio
    return own_audio(AUDIO) + captured_audio(AUDIO)


def _gpu() -> bool:
    from shuper_whisper import transcriber
    return transcriber.select_compute("auto")[0] == "cuda"


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_invented_words_within_budget(scenario, bench, dictionary, request):
    device, live, slow = SCENARIOS[scenario]
    items = _items()
    if not items:
        pytest.skip("no recordings: python benchmarks/record.py")
    if device == "cuda" and not _gpu():
        pytest.skip("no usable GPU")
    hotwords, replacements = dictionary
    result = bench.run_one(MODEL, device, "int8_float16" if device == "cuda" else "int8", items,
                           skip_live=not live, tune={}, hotwords=hotwords, replacements=replacements,
                           repeat=SEEDS, pace="fixed", seed=0, slow=slow)
    mode = "live" if live else "batch"
    found = [(r["clip"], r["seed"], word) for r in result["clips"] if r["clip"] not in bench.HALLUCINATION
             for word in bench.invented(r["expected"], r[mode]["text"], hotwords)]
    clips = sorted({i[0] for i in items})

    budget = json.load(open(BUDGET, encoding="utf-8")) if os.path.exists(BUDGET) else {}
    if request.config.getoption("--update-budget"):
        budget[scenario] = {"invented": len(found), "clips": clips}
        with open(BUDGET, "w", encoding="utf-8") as f:
            json.dump(budget, f, indent=1)
        return
    allowed = budget.get(scenario)
    detail = "\n".join(f"  {clip} (seed {seed}): {word}" for clip, seed, word in found)
    assert allowed, f"no budget for {scenario}: run with --update-budget\n{detail}"
    assert allowed["clips"] == clips, (
        "the recordings changed since the budget was set: check the words below, then "
        f"--update-budget\n{detail}")
    assert len(found) <= allowed["invented"], (
        f"{len(found)} invented words, budget {allowed['invented']}:\n{detail}")
