# Model benchmark 2026-11-05-1030-cuda-int8_float16-base-dict-period: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --set own --models base.en --repeat 3 --pace fixed --hotwords Mackinaw, claude.md, shuper, onebynine, gitea. --label base-dict-period`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `base.en` | 289 / 1751 MB | 3.9 s | 168 / 409 / 504 ms | 0.5 / 1.5 s | 84 |
## Invented words

Words typed that weren't said, per 1000 words said. Dictionary: Mackinaw, claude.md, shuper, onebynine, gitea.. Live: 3 run(s) per clip, pace fixed.

| Model | Type-on-stop | Live typing |
|---|---|---|
| `base.en` | 1.3 (1) | 2.6 (6) |

- `base.en` stop own-23-pause (seed 0): +over
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
| `base.en` | 2.4% -> 2.6% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Your voice | Invented words |
|---|---|---|
| `base.en` | 23 / 7 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `base.en` |
|---|---|
| own | 3% (23/7) |
