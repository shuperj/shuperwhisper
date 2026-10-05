# Model benchmark 2026-10-05-1345-cuda-int8_float16-full: cuda int8_float16 NVIDIA GeForce RTX 3080

Command: `python benchmarks/bench.py --label full`

## Memory and speed

| Model | VRAM loaded / peak | Load | One live pass, 3 s / 10 s / 25 s of audio | Typing lag, median / worst | Backspaces per 100 words |
|---|---|---|---|---|---|
| `large-v3-turbo` | 1217 / 1460 MB | 4.2 s | 148 / 237 / 369 ms | 0.1 / 1.7 s | 126 |
| `distil-medium.en` | 705 / 915 MB | 3.5 s | 86 / 135 / 204 ms | 0.1 / 2.3 s | 117 |
| `small.en` | 481 / 920 MB | 1.8 s | 127 / 395 / 649 ms | 0.2 / 4.1 s | 157 |
| `small` | 481 / 1162 MB | 1.8 s | 133 / 321 / 606 ms | 0.3 / 7.3 s | 123 |
| `distil-small.en` | 391 / 761 MB | 1.7 s | 84 / 206 / 363 ms | 0.1 / 3.8 s | 146 |
| `base.en` | 286 / 571 MB | 1.3 s | 71 / 176 / 355 ms | 0.5 / 5.8 s | 217 |
| `base` | 285 / 899 MB | 1.3 s | 79 / 219 / 418 ms | 0.3 / 2.6 s | 121 |
| `tiny.en` | 201 / 369 MB | 1.2 s | 58 / 144 / 257 ms | 0.2 / 2.9 s | 144 |
| `tiny` | 267 / 375 MB | 1.2 s | 50 / 139 / 267 ms | 0.1 / 2.9 s | 157 |

## Word error rate

Type-on-stop -> live typing. Lower is better.

| Model | Synthetic, clean | Synthetic, 10 dB noise | Synthetic, 3 dB noise | LibriSpeech clean | LibriSpeech other | Sermons |
|---|---|---|---|---|---|---|
| `large-v3-turbo` | 0.0% -> 0.0% | 0.4% -> 2.5% | 0.8% -> 0.8% | 0.8% -> 0.8% | 4.2% -> 11.1% | 4.2% -> 4.1% |
| `distil-medium.en` | 0.4% -> 1.6% | 0.4% -> 1.2% | 1.2% -> 2.9% | 1.0% -> 1.5% | 11.1% -> 14.6% | 6.4% -> 17.2% |
| `small.en` | 0.1% -> 0.3% | 0.4% -> 0.8% | 0.4% -> 1.2% | 1.3% -> 0.8% | 12.2% -> 15.0% | 7.8% -> 8.8% |
| `small` | 0.8% -> 0.8% | 0.8% -> 1.6% | 0.8% -> 2.9% | 0.8% -> 1.5% | 10.5% -> 14.6% | 5.5% -> 9.4% |
| `distil-small.en` | 1.4% -> 1.1% | 2.9% -> 2.9% | 2.0% -> 2.0% | 1.0% -> 1.3% | 11.8% -> 18.5% | 6.7% -> 19.2% |
| `base.en` | 0.5% -> 3.0% | 0.0% -> 6.1% | 3.7% -> 7.4% | 1.8% -> 2.8% | 20.9% -> 25.4% | 7.6% -> 12.3% |
| `base` | 1.2% -> 0.8% | 2.9% -> 2.0% | 2.5% -> 6.1% | 1.8% -> 4.0% | 17.1% -> 23.3% | 5.9% -> 13.4% |
| `tiny.en` | 0.8% -> 1.4% | 2.0% -> 2.5% | 2.0% -> 6.1% | 3.8% -> 8.8% | 24.0% -> 35.2% | 8.9% -> 14.6% |
| `tiny` | 1.2% -> 1.4% | 2.9% -> 3.3% | 4.5% -> 15.6% | 3.3% -> 9.6% | 24.7% -> 35.2% | 8.5% -> 14.8% |

## Sentence breaks and invented text (live typing)

False breaks (a sentence ended mid-sentence) / missed breaks (a real sentence end lost). Invented: words typed for the silence clip plus extra words around the quiet stretch.

| Model | Synthetic, clean | Synthetic, 10 dB noise | Synthetic, 3 dB noise | Sermons | Invented words |
|---|---|---|---|---|---|
| `large-v3-turbo` | 3 / 13 | 1 / 4 | 1 / 2 | 8 / 21 | 0 |
| `distil-medium.en` | 3 / 2 | 0 / 1 | 0 / 1 | 12 / 54 | 0 |
| `small.en` | 5 / 8 | 0 / 4 | 2 / 1 | 4 / 35 | 0 |
| `small` | 4 / 3 | 1 / 2 | 2 / 1 | 4 / 29 | 0 |
| `distil-small.en` | 5 / 1 | 2 / 0 | 1 / 1 | 9 / 41 | 0 |
| `base.en` | 7 / 7 | 3 / 3 | 3 / 2 | 7 / 33 | 1 |
| `base` | 7 / 7 | 2 / 2 | 2 / 1 | 4 / 52 | 0 |
| `tiny.en` | 13 / 6 | 3 / 1 | 1 / 1 | 11 / 43 | 0 |
| `tiny` | 9 / 7 | 2 / 2 | 3 / 2 | 11 / 47 | 0 |

## Live word error rate by clip

Synthetic clips over all their voices; real speech by set. (x/y) = false / missed breaks.

| Clip | `large-v3-turbo` | `distil-medium.en` | `small.en` | `small` | `distil-small.en` | `base.en` | `base` | `tiny.en` | `tiny` |
|---|---|---|---|---|---|---|---|---|---|
| email | 0% (0/2) | 0% | 0% (0/1) | 0% (1/0) | 0% (2/0) | 4% | 0% (0/1) | 1% (1/0) | 19% (0/3) |
| pause_mid | 0% (3/1) | 1% (2/0) | 2% (3/0) | 0% (3/0) | 1% (2/0) | 2% (4/0) | 2% (3/0) | 2% (4/0) | 1% (5/0) |
| pause_mid2 | 0% (1/0) | 0% (1/0) | 0% (4/0) | 0% (2/0) | 0% (3/0) | 0% (6/0) | 4% (5/0) | 1% (4/0) | 2% (3/0) |
| pause_breaks | 6% (0/9) | 5% (0/3) | 0% (0/6) | 2% (0/1) | 1% (0/1) | 18% (0/7) | 2% (0/3) | 10% (0/1) | 2% |
| questions | 2% | 5% | 1% | 3% | 4% | 19% | 4% | 3% | 5% |
| names | 0% (0/1) | 9% | 4% | 6% | 11% | 5% | 5% | 9% | 10% (0/1) |
| alright | 0% (0/6) | 0% | 0% (0/5) | 0% (0/3) | 0% | 0% (1/5) | 0% (1/5) | 0% (0/5) | 0% (0/5) |
| thinking | 0% (1/0) | 0% | 0% | 0% (1/1) | 1% (1/0) | 0% | 5% | 0% (3/1) | 4% (3/1) |
| long | 0% | 0% | 0% | 1% | 0% | 1% (2/0) | 1% (2/0) | 1% (5/0) | 1% (3/0) |
| gap_clicks | 0% | 0% (0/1) | 0% (0/1) | 4% (0/1) | 0% (0/1) | 4% | 0% (0/1) | 0% (0/1) | 0% (0/1) |
| silence | 0 words | 0 words | 0 words | 0 words | 0 words | 0 words | 0 words | 0 words | 0 words |
| sermon | 4% (8/21) | 17% (12/54) | 9% (4/35) | 9% (4/29) | 19% (9/41) | 12% (7/33) | 13% (4/52) | 15% (11/43) | 15% (11/47) |
| libri_clean | 1% | 2% | 1% | 2% | 1% | 3% | 4% | 9% | 10% |
| libri_other | 11% | 15% | 15% | 15% | 18% | 25% | 23% | 35% | 35% |

## Live word error rate by sermon

| Sermon | `large-v3-turbo` | `distil-medium.en` | `small.en` | `small` | `distil-small.en` | `base.en` | `base` | `tiny.en` | `tiny` |
|---|---|---|---|---|---|---|---|---|---|
| black-baptist-brown | 4% | 20% | 23% | 15% | 15% | 15% | 14% | 20% | 18% |
| black-baptist-fmbc | 8% | 12% | 14% | 15% | 10% | 23% | 34% | 29% | 28% |
| contemporary-large | 3% | 15% | 6% | 6% | 10% | 9% | 7% | 13% | 9% |
| contemporary-small | 5% | 14% | 6% | 6% | 17% | 8% | 7% | 13% | 17% |
| follow-church | 2% | 19% | 5% | 5% | 46% | 10% | 6% | 9% | 9% |
| liturgical | 2% | 27% | 2% | 2% | 6% | 12% | 11% | 4% | 7% |
| non-us-accent | 5% | 17% | 7% | 22% | 24% | 17% | 30% | 18% | 17% |
