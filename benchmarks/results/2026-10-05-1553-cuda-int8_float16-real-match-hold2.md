# Model benchmark 2026-10-05-1553-cuda-int8_float16-real-match-hold2: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --models large-v3-turbo --set real --label real-match-hold2`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `large-v3-turbo` | 1217 / 1520 MB | 4.2 s | 202 / 320 / 469 ms | 0.3 / 1.9 s | 150 |

## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | LibriSpeech clean | LibriSpeech other | Sermons |
|---|---|---|---|
| `large-v3-turbo` | 0.8% -> 0.8% | 4.2% -> 8.7% | 4.2% -> 4.9% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Sermons | Invented words |
|---|---|---|
| `large-v3-turbo` | 8 / 22 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `large-v3-turbo` |
|---|---|
| sermon | 5% (8/22) |
| libri_clean | 1% |
| libri_other | 9% |

## Live word error rate by sermon

| Sermon | `large-v3-turbo` |
|---|---|
| black-baptist-brown | 6% |
| black-baptist-fmbc | 14% |
| contemporary-large | 5% |
| contemporary-small | 5% |
| follow-church | 2% |
| liturgical | 2% |
| non-us-accent | 2% |
