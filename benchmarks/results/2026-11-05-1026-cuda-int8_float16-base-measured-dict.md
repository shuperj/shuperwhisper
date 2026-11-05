# Model benchmark 2026-11-05-1026-cuda-int8_float16-base-measured-dict: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --set own --models base.en --label base-measured-dict`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `base.en` | 331 / 1421 MB | 1.7 s | 76 / 193 / 393 ms | 1.0 / 13.5 s | 69 |
## Invented words

Words typed that weren't said, per 1000 words said. Dictionary: Mackinaw, claude.md, shuper, onebynine, gitea. Live: 1 run(s) per clip, pace measured.

| Model | Type-on-stop | Live typing |
|---|---|---|
| `base.en` | 1.3 (1) | 3.9 (3) |

- `base.en` stop own-23-pause (seed 0): +over
- `base.en` live own-03-thinking (seed 0): +it
- `base.en` live own-21-update (seed 0): +is
- `base.en` live own-23-pause (seed 0): +over


## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Your voice |
|---|---|
| `base.en` | 2.4% -> 2.4% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Your voice | Invented words |
|---|---|---|
| `base.en` | 1 / 10 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `base.en` |
|---|---|
| own | 2% (1/10) |
