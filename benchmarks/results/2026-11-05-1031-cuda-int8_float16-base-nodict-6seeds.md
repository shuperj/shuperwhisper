# Model benchmark 2026-11-05-1031-cuda-int8_float16-base-nodict-6seeds: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --set own --models base.en --repeat 6 --pace fixed --hotwords none --label base-nodict-6seeds`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `base.en` | 325 / 1402 MB | 5.7 s | 159 / 518 / 1238 ms | 0.2 / 2.0 s | 122 |
## Invented words

Words typed that weren't said, per 1000 words said. Dictionary: none. Live: 6 run(s) per clip, pace fixed.

| Model | Type-on-stop | Live typing |
|---|---|---|
| `base.en` | 1.3 (1) | 4.9 (23) |

- `base.en` stop own-23-pause (seed 0): +over
- `base.en` live own-19-client (seed 1): +science
- `base.en` live own-19-client (seed 2): +silence
- `base.en` live own-21-update (seed 0): +once we
- `base.en` live own-21-update (seed 1): +once we
- `base.en` live own-21-update (seed 3): +once we
- `base.en` live own-21-update (seed 4): +once we
- `base.en` live own-21-update (seed 5): +once we
- `base.en` live own-23-pause (seed 0): +over
- `base.en` live own-23-pause (seed 1): +over
- `base.en` live own-23-pause (seed 2): +over
- `base.en` live own-23-pause (seed 3): +over
- `base.en` live own-23-pause (seed 4): +over
- `base.en` live own-23-pause (seed 5): +over
- `base.en` live own-25-schedule (seed 0): +is
- `base.en` live own-25-schedule (seed 1): +is
- `base.en` live own-25-schedule (seed 2): +is
- `base.en` live own-25-schedule (seed 4): +is
- `base.en` live own-25-schedule (seed 5): +is


## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Your voice |
|---|---|
| `base.en` | 2.1% -> 2.4% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Your voice | Invented words |
|---|---|---|
| `base.en` | 45 / 12 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `base.en` |
|---|---|
| own | 2% (45/12) |
