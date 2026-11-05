# Model benchmark 2026-11-05-1052-cuda-int8_float16-base-after-x2.5: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --set own --models base.en --repeat 3 --pace fixed --slow 2.5 --label base-after-x2.5`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `base.en` | 295 / 975 MB | 1.9 s | 93 / 209 / 480 ms | 0.5 / 1.9 s | 88 |
## Invented words

Words typed that weren't said, per 1000 words said. Dictionary: Mackinaw, claude.md, shuper, onebynine, gitea.. Live: 3 run(s) per clip, pace fixed x2.5.

| Model | Type-on-stop | Live typing |
|---|---|---|
| `base.en` | 3.8 (3) | 3.8 (9) |

- `base.en` stop own-23-pause (seed 0): +over
- `base.en` stop own-28-dict-gitea (seed 0): +to you
- `base.en` live own-23-pause (seed 0): +over
- `base.en` live own-23-pause (seed 1): +over
- `base.en` live own-23-pause (seed 2): +over
- `base.en` live own-28-dict-gitea (seed 0): +to you
- `base.en` live own-28-dict-gitea (seed 1): +to you
- `base.en` live own-28-dict-gitea (seed 2): +to you


## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Your voice |
|---|---|
| `base.en` | 2.8% -> 2.6% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Your voice | Invented words |
|---|---|---|
| `base.en` | 25 / 6 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `base.en` |
|---|---|
| own | 3% (25/6) |
