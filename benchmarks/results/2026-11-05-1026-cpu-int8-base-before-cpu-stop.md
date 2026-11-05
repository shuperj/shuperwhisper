# Model benchmark 2026-11-05-1026-cpu-int8-base-before-cpu-stop: cpu int8

Command: `python benchmarks/bench.py --set own --models base.en --device cpu --skip-live --label base-before-cpu-stop`

## Memory and speed

| Model | RAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio |
|---|---|---|---|
| `base.en` | 0 / 0 MB | 1.6 s | 657 / 857 / 1326 ms |
## Invented words

Words typed that weren't said, per 1000 words said. Dictionary: Mackinaw, claude.md, shuper, onebynine, gitea. Live: 1 run(s) per clip, pace measured.

| Model | Type-on-stop | Live typing |
|---|---|---|
| `base.en` | 1.3 (1) | - |

- `base.en` stop own-23-pause (seed 0): +over


## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Your voice |
|---|---|
| `base.en` | 2.1% |
