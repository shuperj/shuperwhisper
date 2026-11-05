# Model benchmark 2026-11-05-1042-cuda-int8_float16-base-silence-dictperiod: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --set synthetic --clips silence gap --models base.en --repeat 3 --pace fixed --label base-silence-dictperiod`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `base.en` | 288 / 563 MB | 2.7 s | 127 / 310 / 684 ms | 1.4 / 1.6 s | 216 |
## Invented words

Words typed that weren't said, per 1000 words said. Dictionary: Mackinaw, claude.md, shuper, onebynine, gitea.. Live: 3 run(s) per clip, pace fixed.

| Model | Type-on-stop | Live typing |
|---|---|---|
| `base.en` | - | - |


## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Synthetic, clean |
|---|---|
| `base.en` | - -> - |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Synthetic, clean | Invented words |
|---|---|---|
| `base.en` | 0 / 0 | 3 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `base.en` |
|---|---|
| gap_clicks | 4% |
| silence | 0 words |
