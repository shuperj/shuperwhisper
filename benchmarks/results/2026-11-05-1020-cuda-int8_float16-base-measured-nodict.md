# Model benchmark 2026-11-05-1020-cuda-int8_float16-base-measured-nodict: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --set own --models base.en --hotwords none --label base-measured-nodict`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `base.en` | 285 / 536 MB | 1.7 s | 122 / 327 / 653 ms | 0.2 / 4.0 s | 160 |
## Invented words

Words typed that weren't said, per 1000 words said. Dictionary: none. Live: 1 run(s) per clip, pace measured.

| Model | Type-on-stop | Live typing |
|---|---|---|
| `base.en` | 1.3 (1) | 3.9 (3) |

- `base.en` stop own-23-pause (seed 0): +over
- `base.en` live own-21-update (seed 0): +once we
- `base.en` live own-23-pause (seed 0): +over


## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Your voice |
|---|---|
| `base.en` | 2.1% -> 2.2% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Your voice | Invented words |
|---|---|---|
| `base.en` | 9 / 2 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `base.en` |
|---|---|
| own | 2% (9/2) |
