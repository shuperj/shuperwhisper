# Model benchmark

Compares Whisper models on what matters for ShuperWhisper (memory, speed, and how
well dictation comes out) through the app's own code. It doubles as a tuning tool
for the live-typing settings.

```bash
pip install regex more-itertools                            # the text normaliser's two deps
python benchmarks/bench.py                                  # all models, all clips, GPU (int8_float16)
python benchmarks/bench.py --device cpu --models base.en small.en
python benchmarks/bench.py --models large-v3-turbo --compute float16
python benchmarks/bench.py --models large-v3-turbo --set synthetic --clips pause --tune JOIN_GAP=0.4
python benchmarks/record.py                                 # add your own voice
```

Each model runs in its own process. Results go to `benchmarks/results/<run>.md`
(raw JSON per model under `results/raw/`, gitignored). `--summarise results/raw/<run>`
re-scores a finished run from its stored text, so scoring changes apply to old runs.

Options: `--set all|synthetic|real`, `--clips <id prefix>...`, `--variants david sermon ...`,
`--skip-live` (type-on-stop only), `--tune NAME=VALUE` (any `StreamingSession`
setting), `--label` (added to the file name).

## What is measured

- **VRAM (or RAM) loaded / peak**: whole-GPU memory above what was in use before the
  model process started, so it includes the CUDA context (~250 MB).
- **Load**: seconds to load (the first run also downloads the model).
- **One live pass, 3 s / 10 s / 25 s**: one greedy decode of that much audio. Live typing
  re-decodes the current utterance every 0.4 s on GPU and 1 s on CPU, and an utterance is
  at most 25 s, so a model much slower than that at 25 s falls behind.
- **Typing lag**: from the end of speech until the field stops changing.
- **Backspaces per 100 words**: how much the live text rewrites itself.
- **Word error rate**: substitutions, deletions and insertions per reference word,
  after Whisper's English normaliser (vendored in `_whisper_normalizer/`, MIT, as in
  asr-shootout), so casing, punctuation, number style and fillers don't count.
  Shown as type-on-stop (`Transcriber.transcribe`, beam 5, then the text rules) ->
  live typing (`StreamingSession` + `LiveWriter` into a fake field, in simulated real
  time: the clock advances by the poll interval plus however long each step took).
- **False / missed breaks**: a sentence ended where it shouldn't ("out. Right now.")
  or a real sentence end was lost.
- **Invented words**: anything typed for 10 s of room noise with clicks, plus extra
  words around a 12 s quiet stretch (Whisper's hallucinations).

## Clips

**Synthetic** (`corpus.py`, rendered with Windows' speech synthesiser, cached in
`.audio/`): nine sentences (an email, mid-sentence pauses, real sentence breaks after
pauses, questions, product names, thinking pauses, a 30 s run-on that hits the
utterance cap), each as David, Zira, Zira faster, David with pink noise at 10 dB SNR,
and Zira at 3 dB. Plus the silence and quiet-stretch clips. Synthetic voices are easy:
they separate models on punctuation, breaks and speed more than on words.

**Real** (`.audio/real/`, cut from the asr-shootout corpus by `extract_real.py`, which
runs on the sermons CT where that audio lives):

- 28 segments of 12-25 s from the seven sermons with a human-verified answer key, cut
  at sentence ends, speech only: Black Baptist (two), contemporary (two), liturgical,
  Follow Church and a Nigerian-English preacher. The keys are punctuated and verbatim
  (they keep "I'm I'm" repeats, which Whisper and the app tidy away, so WER here is
  higher than the words actually wrong).
- 24 LibriSpeech utterances of 5-20 s, half `test-clean`, half the harder `test-other`.
  Unpunctuated references, so words only.

The sermon audio is for internal testing only: it stays in the gitignored `.audio/`.
To rebuild it: `scp benchmarks/extract_real.py` to the CT, run
`python3 extract_real.py ~/apps/asr-shootout/corpus /tmp/sw_real`, and copy
`/tmp/sw_real` back as `benchmarks/.audio/real`.

**Your voice** (`record.py`): reads the nine synthetic sentences through the microphone
ShuperWhisper uses into `.audio/own/`; scored as the "Your voice" column.
