# Model benchmark 2026-11-05-1012-cuda-int8_float16-base-before-x1: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --set own --models base.en --repeat 3 --pace fixed --label base-before-x1`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `base.en` | 289 / 1963 MB | 1.9 s | 74 / 198 / 411 ms | 0.2 / 1.8 s | 96 |
## Invented words

Words typed that weren't said, per 1000 words said. Dictionary: Mackinaw, claude.md, shuper, onebynine, gitea. Live: 3 run(s) per clip, pace fixed.

| Model | Type-on-stop | Live typing |
|---|---|---|
| `base.en` | 1.3 (1) | 13.7 (32) |

- `base.en` stop own-23-pause (seed 0): +over
- `base.en` live own-03-thinking (seed 0): +it
- `base.en` live own-03-thinking (seed 1): +it
- `base.en` live own-03-thinking (seed 2): +it
- `base.en` live own-19-client (seed 0): +and i will see you in the next one
- `base.en` live own-19-client (seed 1): +.
- `base.en` live own-19-client (seed 2): +and then we will see you in the next one
- `base.en` live own-21-update (seed 0): +once we
- `base.en` live own-21-update (seed 1): +once we
- `base.en` live own-21-update (seed 2): +is
- `base.en` live own-23-pause (seed 0): +over
- `base.en` live own-23-pause (seed 1): +over
- `base.en` live own-23-pause (seed 2): +over
- `base.en` live own-25-schedule (seed 1): +is


## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Your voice |
|---|---|
| `base.en` | 2.4% -> 3.6% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Your voice | Invented words |
|---|---|---|
| `base.en` | 6 / 32 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `base.en` |
|---|---|
| own | 4% (6/32) |
