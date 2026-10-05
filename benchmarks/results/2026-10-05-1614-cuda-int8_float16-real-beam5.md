# Model benchmark 2026-10-05-1614-cuda-int8_float16-real-beam5: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --models large-v3-turbo --set real --variants libri_other sermon --tune BEAM=5 --label real-beam5`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `large-v3-turbo` | 1217 / 1459 MB | 4.6 s | 133 / 215 / 323 ms | 0.4 / 1.8 s | 129 |

## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | LibriSpeech other | Sermons |
|---|---|---|
| `large-v3-turbo` | 4.2% -> 7.3% | 4.2% -> 4.2% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Sermons | Invented words |
|---|---|---|
| `large-v3-turbo` | 4 / 38 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `large-v3-turbo` |
|---|---|
| sermon | 4% (4/38) |
| libri_other | 7% |

## Live word error rate by sermon

| Sermon | `large-v3-turbo` |
|---|---|
| black-baptist-brown | 4% |
| black-baptist-fmbc | 8% |
| contemporary-large | 4% |
| contemporary-small | 5% |
| follow-church | 5% |
| liturgical | 1% |
| non-us-accent | 2% |
