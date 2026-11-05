# Model benchmark 2026-11-05-1056-cuda-int8_float16-dictcheck-none: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --set own --clips own-28 own-29 own-30 own-31 own-32 own-33 own-34 own-35 own-36 --models base.en --repeat 3 --pace fixed --hotwords none --label dictcheck-none`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `base.en` | 290 / 497 MB | 1.6 s | 112 / 295 / 610 ms | 0.3 / 0.5 s | 134 |
## Invented words

Words typed that weren't said, per 1000 words said. Dictionary: none. Live: 3 run(s) per clip, pace fixed.

| Model | Type-on-stop | Live typing |
|---|---|---|
| `base.en` | 29.4 (4) | 29.4 (12) |

- `base.en` stop own-28-dict-gitea (seed 0): +to you
- `base.en` stop own-31-dict-onebynine (seed 0): +x 9
- `base.en` live own-28-dict-gitea (seed 0): +to you
- `base.en` live own-28-dict-gitea (seed 1): +to you
- `base.en` live own-28-dict-gitea (seed 2): +to you
- `base.en` live own-31-dict-onebynine (seed 0): +x 9
- `base.en` live own-31-dict-onebynine (seed 1): +x 9
- `base.en` live own-31-dict-onebynine (seed 2): +x 9


## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Your voice |
|---|---|
| `base.en` | 8.8% -> 7.8% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Your voice | Invented words |
|---|---|---|
| `base.en` | 0 / 0 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `base.en` |
|---|---|
| own | 8% |
