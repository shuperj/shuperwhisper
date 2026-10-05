# Model benchmark 2026-10-05-1703-cuda-int8_float16-own-voice: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --set own --label own-voice`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `large-v3-turbo` | 1178 / 1568 MB | 7.2 s | 263 / 487 / 714 ms | 0.3 / 0.9 s | 66 |
| `distil-medium.en` | 786 / 957 MB | 5.8 s | 131 / 227 / 381 ms | 0.2 / 1.7 s | 41 |
| `small.en` | 466 / 919 MB | 4.9 s | 273 / 883 / 1518 ms | 0.7 / 6.8 s | 58 |
| `small` | 495 / 1085 MB | 5.4 s | 304 / 796 / 1335 ms | 0.6 / 3.5 s | 65 |
| `distil-small.en` | 372 / 864 MB | 5.0 s | 148 / 372 / 649 ms | 0.2 / 0.6 s | 64 |
| `base.en` | 289 / 662 MB | 2.3 s | 157 / 405 / 889 ms | 0.3 / 5.8 s | 186 |
| `base` | 290 / 487 MB | 2.4 s | 165 / 477 / 860 ms | 0.3 / 4.6 s | 56 |
| `tiny.en` | 239 / 382 MB | 2.1 s | 90 / 255 / 480 ms | 0.1 / 1.5 s | 69 |
| `tiny` | 257 / 437 MB | 2.1 s | 100 / 290 / 506 ms | 0.2 / 3.9 s | 110 |

## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Your voice |
|---|---|
| `large-v3-turbo` | 1.4% -> 1.4% |
| `distil-medium.en` | 2.4% -> 4.4% |
| `small.en` | 1.3% -> 2.1% |
| `small` | 1.8% -> 1.3% |
| `distil-small.en` | 1.4% -> 1.9% |
| `base.en` | 2.1% -> 2.3% |
| `base` | 2.3% -> 4.3% |
| `tiny.en` | 1.9% -> 4.4% |
| `tiny` | 2.6% -> 3.0% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Your voice | Invented words |
|---|---|---|
| `large-v3-turbo` | 4 / 2 | 0 |
| `distil-medium.en` | 3 / 15 | 0 |
| `small.en` | 5 / 3 | 0 |
| `small` | 6 / 4 | 0 |
| `distil-small.en` | 7 / 3 | 0 |
| `base.en` | 7 / 2 | 0 |
| `base` | 8 / 6 | 0 |
| `tiny.en` | 6 / 2 | 0 |
| `tiny` | 6 / 8 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `large-v3-turbo` | `distil-medium.en` | `small.en` | `small` | `distil-small.en` | `base.en` | `base` | `tiny.en` | `tiny` |
|---|---|---|---|---|---|---|---|---|---|
| own | 1% (4/2) | 4% (3/15) | 2% (5/3) | 1% (6/4) | 2% (7/3) | 2% (7/2) | 4% (8/6) | 4% (6/2) | 3% (6/8) |
