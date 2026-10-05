# Model benchmark 2026-10-05-1319-cuda-int8_float16-sermons-new-jg0.4: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --models large-v3-turbo --set real --variants sermon --tune JOIN_GAP=0.4 --label sermons-new-jg0.4`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `large-v3-turbo` | 1217 / 1459 MB | 4.2 s | 143 / 233 / 345 ms | 0.4 / 1.6 s | 99 |

## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Sermons |
|---|---|
| `large-v3-turbo` | 4.2% -> 4.4% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Sermons | Invented words |
|---|---|---|
| `large-v3-turbo` | 10 / 26 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `large-v3-turbo` |
|---|---|
| sermon | 4% (10/26) |

## Live word error rate by sermon

| Sermon | `large-v3-turbo` |
|---|---|
| black-baptist-brown | 4% |
| black-baptist-fmbc | 9% |
| contemporary-large | 6% |
| contemporary-small | 4% |
| follow-church | 3% |
| liturgical | 2% |
| non-us-accent | 4% |
