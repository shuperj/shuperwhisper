"""Benchmark clips: what is said (SSML for Windows' speech synthesiser) and
what a perfect dictation would type.

Synthetic speech is cleaner than a real voice through a real mic, so absolute
error rates here are optimistic; the comparison between models is what counts.
The "noisy" variant and the pause/gap clips push in the direction of real use.
"""

import json
import os
import subprocess
from dataclasses import dataclass

import numpy as np

SR = 16000


@dataclass(frozen=True)
class Clip:
    id: str
    ssml: str        # body of a <speak> element; <break time="..."/> for pauses
    expected: str    # what should end up in the field


def _brk(ms: int) -> str:
    return f'<break time="{ms}ms"/>'


CLIPS = [
    Clip("email",
         "Hey Dana, I wanted to follow up on the quarterly report. Can you send me the updated "
         "numbers by Friday afternoon? Thanks, and let me know if anything changes.",
         "Hey Dana, I wanted to follow up on the quarterly report. Can you send me the updated "
         "numbers by Friday afternoon? Thanks, and let me know if anything changes."),
    Clip("pause_mid",
         f"Hey, I am just testing things out {_brk(1100)} right now. Yeah, so I am basically making "
         f"some sentences, {_brk(900)} and whatnot.",
         "Hey, I am just testing things out right now. Yeah, so I am basically making some "
         "sentences, and whatnot."),
    Clip("pause_mid2",
         f"I think we should move the meeting {_brk(1200)} to next Tuesday, because half the team "
         f"is out {_brk(1000)} on Monday.",
         "I think we should move the meeting to next Tuesday, because half the team is out on Monday."),
    Clip("pause_breaks",
         f"The build passed on the first try. {_brk(1200)} We still need to update the documentation. "
         f"{_brk(1000)} I will take care of that tomorrow.",
         "The build passed on the first try. We still need to update the documentation. I will take "
         "care of that tomorrow."),
    Clip("questions",
         "Did you get a chance to look at the pull request? What do you think about the new "
         "settings page?",
         "Did you get a chance to look at the pull request? What do you think about the new "
         "settings page?"),
    Clip("names",
         "The settings window uses React and Tailwind, and the backend is written in Python. "
         "Jared wants it on GitHub by Thursday.",
         "The settings window uses React and Tailwind, and the backend is written in Python. "
         "Jared wants it on GitHub by Thursday."),
    Clip("alright",
         f"Alright. {_brk(1000)} So I am testing everything here, and it seems to work.",
         "Alright. So I am testing everything here, and it seems to work."),
    Clip("thinking",
         f"So the plan is {_brk(1500)} we ship the installer first, {_brk(1300)} and then we look at "
         f"the settings page {_brk(1400)} once people have tried it.",
         "So the plan is we ship the installer first, and then we look at the settings page once "
         "people have tried it."),
    Clip("long",
         "When I got to the office this morning the coffee machine was broken again, so I walked "
         "down to the place on the corner and waited in a line that went out the door, and by the "
         "time I got back the standup had already started and everyone was talking about the "
         "release that we were supposed to ship last week but that still has a handful of bugs "
         "that nobody has had time to look at properly.",
         "When I got to the office this morning the coffee machine was broken again, so I walked "
         "down to the place on the corner and waited in a line that went out the door, and by the "
         "time I got back the standup had already started and everyone was talking about the "
         "release that we were supposed to ship last week but that still has a handful of bugs "
         "that nobody has had time to look at properly."),
]

# Built from the clips above plus room noise (see build_audio).
GAP_CLIP = Clip("gap_clicks", "", "Hey Dana, I wanted to follow up on the quarterly report. "
                "The build passed on the first try. We still need to update the documentation.")
SILENCE_CLIP = Clip("silence", "", "")
_GAP_PARTS = ("Hey Dana, I wanted to follow up on the quarterly report.",
              "The build passed on the first try. We still need to update the documentation.")

# (name, voice, rate -10..10, signal-to-noise ratio in dB of added pink noise or None)
VARIANTS = [
    ("david", "Microsoft David Desktop", 0, None),
    ("zira", "Microsoft Zira Desktop", 0, None),
    ("zira_fast", "Microsoft Zira Desktop", 3, None),
    ("david_noisy", "Microsoft David Desktop", 0, 10),   # a fan, a busy room
    ("zira_noisy", "Microsoft Zira Desktop", 0, 3),      # very noisy
]

_PS = r"""
Add-Type -AssemblyName System.Speech
$jobs = Get-Content -Raw -Encoding UTF8 $args[0] | ConvertFrom-Json
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($j in $jobs) {
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice($j.voice); $s.Rate = $j.rate
  $s.SetOutputToWaveFile($j.path, $fmt)
  $s.SpeakSsml('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">' + $j.ssml + '</speak>')
  $s.Dispose()
}
"""


def _read_wav(path: str) -> np.ndarray:
    import wave
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def _write_wav(path: str, audio: np.ndarray) -> None:
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


def _room(seconds: float, rng, clicks=()) -> np.ndarray:
    """Quiet room noise with a few clicks (mouse, keys)."""
    noise = (rng.standard_normal(int(seconds * SR)) * 0.003).astype(np.float32)
    for t in clicks:
        i = int(t * SR)
        noise[i:i + 300] += (rng.standard_normal(300) * 0.4).astype(np.float32)
    return noise


def _pink(n: int, rng) -> np.ndarray:
    spectrum = np.fft.rfft(rng.standard_normal(n))
    spectrum /= np.sqrt(np.maximum(np.arange(len(spectrum)), 1))
    pink = np.fft.irfft(spectrum, n)
    return (pink / np.std(pink)).astype(np.float32)


def _add_noise(audio: np.ndarray, snr_db: float, rng) -> np.ndarray:
    speech = audio[np.abs(audio) > 0.01]
    level = np.sqrt(np.mean(speech ** 2)) if len(speech) else 0.05
    return audio + _pink(len(audio), rng) * level / (10 ** (snr_db / 20))


def build_audio(cache_dir: str) -> list[tuple[str, str, str, str]]:
    """Render every clip and variant (cached). Returns (clip id, variant, wav path, expected)."""
    os.makedirs(cache_dir, exist_ok=True)
    jobs, items = [], []
    for name, voice, rate, _snr in VARIANTS:
        clean_name = name.replace("_noisy", "")
        for clip in CLIPS:
            path = os.path.join(cache_dir, f"{clip.id}.{clean_name}.wav")
            if not os.path.exists(path):
                jobs.append({"voice": voice, "rate": rate, "ssml": clip.ssml, "path": path})
    for i, text in enumerate(_GAP_PARTS):
        path = os.path.join(cache_dir, f"gap_part{i}.wav")
        if not os.path.exists(path):
            jobs.append({"voice": VARIANTS[0][1], "rate": 0, "ssml": text, "path": path})
    jobs = list({j["path"]: j for j in jobs}.values())
    if jobs:
        job_file = os.path.join(cache_dir, "jobs.json")
        script = os.path.join(cache_dir, "tts.ps1")
        with open(job_file, "w", encoding="utf-8") as f:
            json.dump(jobs, f)
        with open(script, "w", encoding="utf-8") as f:
            f.write(_PS)
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, job_file],
                       check=True)
    rng = np.random.default_rng(7)
    for name, _voice, _rate, snr in VARIANTS:
        clean_name = name.replace("_noisy", "")
        for clip in CLIPS:
            src = os.path.join(cache_dir, f"{clip.id}.{clean_name}.wav")
            path = os.path.join(cache_dir, f"{clip.id}.{name}.wav")
            if snr is not None and not os.path.exists(path):
                _write_wav(path, _add_noise(_read_wav(src), snr, rng))
            items.append((clip.id, name, path, clip.expected))
    gap = os.path.join(cache_dir, "gap_clicks.wav")
    if not os.path.exists(gap):
        a, b = (_read_wav(os.path.join(cache_dir, f"gap_part{i}.wav")) for i in range(2))
        _write_wav(gap, np.concatenate([a, _room(12, rng, clicks=(1.0, 5.5, 9.0)), b, _room(1, rng)]))
    items.append((GAP_CLIP.id, "david", gap, GAP_CLIP.expected))
    silence = os.path.join(cache_dir, "silence.wav")
    if not os.path.exists(silence):
        _write_wav(silence, _room(10, rng, clicks=(2.0, 6.0)))
    items.append((SILENCE_CLIP.id, "room", silence, ""))
    return items


def own_audio(cache_dir: str) -> list[tuple[str, str, str, str]]:
    """Your voice, recorded with record.py (variant "own")."""
    from own_script import OWN_SCRIPT, expected
    out = []
    for cid, text in OWN_SCRIPT:
        path = os.path.join(cache_dir, "own", f"{cid}.wav")
        if os.path.exists(path):
            out.append((cid, "own", path, expected(text)))
    return out


def real_audio(cache_dir: str) -> list[tuple[str, str, str, str]]:
    """Real speech cut from the asr-shootout corpus by extract_real.py, if present.
    Variants: "sermon" (punctuated keys), "libri_clean" / "libri_other" (words only)."""
    folder = os.path.join(cache_dir, "real")
    manifest = os.path.join(folder, "manifest.json")
    if not os.path.exists(manifest):
        return []
    with open(manifest, encoding="utf-8") as f:
        clips = json.load(f)
    return [(c["id"], c["set"], os.path.join(folder, f"{c['id']}.wav"), c["expected"]) for c in clips]
