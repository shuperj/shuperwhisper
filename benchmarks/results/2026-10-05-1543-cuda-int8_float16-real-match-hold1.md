# Model benchmark 2026-10-05-1543-cuda-int8_float16-real-match-hold1: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --models large-v3-turbo --set real --tune LocalAgreement.HOLD_WORDS=1 --label real-match-hold1`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `large-v3-turbo` | 1219 / 1595 MB | 4.7 s | 192 / 332 / 528 ms | 0.3 / 2.1 s | 130 |

## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | LibriSpeech clean | LibriSpeech other | Sermons |
|---|---|---|---|
| `large-v3-turbo` | 0.8% -> 0.8% | 4.2% -> 8.7% | 4.2% -> 4.1% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Sermons | Invented words |
|---|---|---|
| `large-v3-turbo` | 10 / 20 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `large-v3-turbo` |
|---|---|
| sermon | 4% (10/20) |
| libri_clean | 1% |
| libri_other | 9% |

## Live word error rate by sermon

| Sermon | `large-v3-turbo` |
|---|---|
| black-baptist-brown | 4% |
| black-baptist-fmbc | 9% |
| contemporary-large | 4% |
| contemporary-small | 6% |
| follow-church | 2% |
| liturgical | 2% |
| non-us-accent | 3% |
