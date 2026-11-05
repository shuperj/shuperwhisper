# Model benchmark 2026-11-05-1046-cuda-int8_float16-base-after-x1: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --set own --models base.en --repeat 3 --pace fixed --slow 1 --label base-after-x1`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `base.en` | 901 / 976 MB | 1.8 s | 99 / 257 / 543 ms | 0.2 / 2.1 s | 67 |
## Invented words

Words typed that weren't said, per 1000 words said. Dictionary: Mackinaw, claude.md, shuper, onebynine, gitea.. Live: 3 run(s) per clip, pace fixed.

| Model | Type-on-stop | Live typing |
|---|---|---|
| `base.en` | 1.3 (1) | 3.0 (7) |

- `base.en` stop own-23-pause (seed 0): +over
- `base.en` live own-06-tech (seed 1): +pi
- `base.en` live own-21-update (seed 0): +is
- `base.en` live own-21-update (seed 1): +is
- `base.en` live own-21-update (seed 2): +is
- `base.en` live own-23-pause (seed 0): +over
- `base.en` live own-23-pause (seed 1): +over
- `base.en` live own-23-pause (seed 2): +over


## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Your voice |
|---|---|
| `base.en` | 2.4% -> 2.4% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Your voice | Invented words |
|---|---|---|
| `base.en` | 21 / 6 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `base.en` |
|---|---|
| own | 2% (21/6) |
