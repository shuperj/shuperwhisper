# Stage 1 — Foundation: fixes and removals — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (run inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Voicemeeter "stuck on Loading" bug, make dictated text read like a person typed it, type at the caret without touching the clipboard, run Whisper on the GPU, and delete the format modes and the Claude dependency. The app is still batch at the end of this stage: it transcribes when you press the hotkey a second time.

**Architecture:**
- **Devices.** They are stored by name + host API and resolved to a PortAudio index each time dictation starts. Audio is captured at the device's native rate and resampled to 16 kHz with `soxr`.
- **Text.** A pure `text_rules` module does all text cleanup.
- **Typing.** `SendInput` with `KEYEVENTF_UNICODE` types the text. The caret context comes from UI Automation.
- **Lifecycle.** Every failure ends in `STATE_ERROR` with a message; the app never stays stuck in `STATE_LOADING`.

**Tech Stack:** Python 3.12, faster-whisper 1.2 / ctranslate2 ≥ 4.5, sounddevice, soxr, comtypes (UI Automation), pywebview, React 19 + Vite + Tailwind 4.

**Spec:** `docs/superpowers/specs/2026-10-04-live-dictation-design.md` (Stage 1 section)

## Global Constraints

- Windows 10/11 x64 only. Python ≥ 3.12.
- No AI or network in the text path. Remove the `anthropic` and `pyperclip` dependencies.
- Never write to the clipboard.
- Config stores the input device as `{"name": str, "hostapi": str | None}` or `null`, never as an index (a legacy int is migrated at startup).
- Hotkey is toggle-only: the first press starts, the second press stops.
- Tests: `python -m pytest tests/ -q`. Run them before every commit.
- Conventional commits. End each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- All work happens on branch `feat/stage1-foundation`, which ends as one PR on Gitea. Never merge it.

---

### Task 0: Branch and dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Create the branch**

```bash
cd D:/dev/hobby/projects/shuperwhisper && git checkout -b feat/stage1-foundation
```

- [ ] **Step 2: Update dependencies in `pyproject.toml`**

Replace the `dependencies` list and add the `gpu` extra:

```toml
dependencies = [
    "faster-whisper>=1.2",
    "ctranslate2>=4.5",
    "sounddevice>=0.5",
    "soxr>=0.5",
    "comtypes>=1.4",
    "numpy",
    "pystray>=0.19.5",
    "Pillow>=10.0",
    "pywebview>=5.0.0",
]
```

and in `[project.optional-dependencies]`, add the following after `dev`:

```toml
gpu = [
    "nvidia-cublas-cu12",
    "nvidia-cudnn-cu12>=9,<10",
]
```

- [ ] **Step 3: Install**

```bash
python -m pip install -e ".[dev,gpu]"
```

Expected: `ctranslate2` resolves to ≥ 4.5 (`python -m pip show ctranslate2`), and `soxr`, `comtypes`, `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` are installed.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add soxr, comtypes and the CUDA runtime extra; require ctranslate2>=4.5"
```

---

### Task 1: Slim the config

**Files:**
- Modify: `shuper_whisper/config.py`
- Test: `tests/test_config.py` (rewrite)

**Interfaces:**
- Produces: `AppConfig(hotkey: str = "ctrl+shift+space", model_size: str = "auto", input_device: dict | int | None = None, language: str = "en", overlay_position: str = "top_center")`
- Produces: `AppConfig.VALID_MODELS = ("auto", "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3")`
- Produces: `VALID_OVERLAY_POSITIONS`, `SUPPORTED_LANGUAGES`, `load_config(path=None)`, `save_config(config, path=None)` and `config_dir()`, all unchanged.
- Removed: `VALID_HOTKEY_MODES`, `VALID_FORMAT_MODES`, `FORMAT_MODE_LABELS`, `FORMAT_MODE_ORDER`.

- [ ] **Step 1: Rewrite `tests/test_config.py`**

```python
"""Tests for the slimmed-down config."""

import json

from shuper_whisper.config import (
    VALID_OVERLAY_POSITIONS,
    AppConfig,
    load_config,
    save_config,
)


class TestDefaults:
    def test_defaults(self):
        c = AppConfig()
        assert c.hotkey == "ctrl+shift+space"
        assert c.model_size == "auto"
        assert c.input_device is None
        assert c.language == "en"
        assert c.overlay_position == "top_center"

    def test_removed_fields_are_gone(self):
        d = AppConfig().to_dict()
        for key in ("format_mode", "email_tone", "prompt_detail", "hotkey_mode",
                    "smart_spacing", "bullet_mode", "email_mode",
                    "accent_color", "bg_color"):
            assert key not in d


class TestValidate:
    def test_bad_model_resets_to_auto(self):
        c = AppConfig(model_size="huge")
        c.validate()
        assert c.model_size == "auto"

    def test_turbo_is_valid(self):
        c = AppConfig(model_size="large-v3-turbo")
        c.validate()
        assert c.model_size == "large-v3-turbo"

    def test_empty_hotkey_resets(self):
        c = AppConfig(hotkey="")
        c.validate()
        assert c.hotkey == "ctrl+shift+space"

    def test_unknown_language_resets(self):
        c = AppConfig(language="xx")
        c.validate()
        assert c.language == "en"

    def test_bad_overlay_position_resets(self):
        c = AppConfig(overlay_position="nowhere")
        c.validate()
        assert c.overlay_position == "top_center"

    def test_valid_positions_kept(self):
        for pos in VALID_OVERLAY_POSITIONS:
            c = AppConfig(overlay_position=pos)
            c.validate()
            assert c.overlay_position == pos


class TestInputDevice:
    def test_none_is_default(self):
        c = AppConfig(input_device=None)
        c.validate()
        assert c.input_device is None

    def test_ref_kept(self):
        ref = {"name": "Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO)", "hostapi": "Windows WASAPI"}
        c = AppConfig(input_device=dict(ref))
        c.validate()
        assert c.input_device == ref

    def test_ref_without_hostapi(self):
        c = AppConfig(input_device={"name": "Mic"})
        c.validate()
        assert c.input_device == {"name": "Mic", "hostapi": None}

    def test_legacy_int_kept_for_migration(self):
        c = AppConfig(input_device=75)
        c.validate()
        assert c.input_device == 75

    def test_bool_is_not_an_index(self):
        c = AppConfig(input_device=True)
        c.validate()
        assert c.input_device is None

    def test_legacy_name_string_becomes_ref(self):
        c = AppConfig(input_device="Mic")
        c.validate()
        assert c.input_device == {"name": "Mic", "hostapi": None}

    def test_garbage_becomes_default(self):
        for bad in ({"hostapi": "MME"}, {"name": ""}, [], 3.5, ""):
            c = AppConfig(input_device=bad)
            c.validate()
            assert c.input_device is None, bad


class TestSaveLoad:
    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "config.json")
        ref = {"name": "Mic", "hostapi": "MME"}
        save_config(AppConfig(hotkey="f9", model_size="small", input_device=ref,
                              language="de", overlay_position="center"), path)
        loaded = load_config(path)
        assert (loaded.hotkey, loaded.model_size, loaded.input_device,
                loaded.language, loaded.overlay_position) == ("f9", "small", ref, "de", "center")

    def test_old_config_keys_ignored(self, tmp_path):
        path = str(tmp_path / "config.json")
        with open(path, "w") as f:
            json.dump({"hotkey": "f16", "format_mode": "ai_prompt", "email_tone": 5,
                       "accent_color": "#000000", "input_device": 75}, f)
        loaded = load_config(path)
        assert loaded.hotkey == "f16"
        assert loaded.input_device == 75
        assert not hasattr(loaded, "format_mode")

    def test_missing_file_gives_defaults(self, tmp_path):
        assert load_config(str(tmp_path / "nope.json")).model_size == "auto"
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL. The import errors on removed names, or the defaults don't match.

- [ ] **Step 3: Rewrite the config section of `shuper_whisper/config.py`**

Keep `_is_frozen`, `_appdata_dir`, `_project_root`, `config_dir`, `_default_config_path`, `_default_dictionary_path` and `SUPPORTED_LANGUAGES` as they are. Replace everything from `VALID_HOTKEY_MODES = ...` to the end of the file with:

```python
VALID_OVERLAY_POSITIONS = ("top_center", "center", "bottom_center")


def _validate_device(value: object) -> object:
    """Normalise the stored input device.

    Returns a ``{"name", "hostapi"}`` reference, a legacy int index (migrated to
    a reference at startup by audio_devices.migrate), or None for the default.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return {"name": value, "hostapi": None} if value.strip() else None
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name:
            hostapi = value.get("hostapi")
            return {"name": name, "hostapi": hostapi if isinstance(hostapi, str) else None}
    return None


@dataclass
class AppConfig:
    hotkey: str = "ctrl+shift+space"
    # "auto" picks large-v3-turbo on a CUDA GPU and base on CPU (transcriber.py).
    model_size: str = "auto"
    # {"name": str, "hostapi": str | None}, a legacy int index, or None for default.
    input_device: object = None
    language: str = "en"
    overlay_position: str = "top_center"

    VALID_MODELS = ("auto", "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3")

    def validate(self) -> None:
        if self.model_size not in self.VALID_MODELS:
            self.model_size = "auto"
        if not self.hotkey:
            self.hotkey = "ctrl+shift+space"
        if self.language not in SUPPORTED_LANGUAGES:
            self.language = "en"
        if self.overlay_position not in VALID_OVERLAY_POSITIONS:
            self.overlay_position = "top_center"
        self.input_device = _validate_device(self.input_device)

    def to_dict(self) -> dict:
        return asdict(self)


_CONFIG_FIELDS = ["hotkey", "model_size", "input_device", "language", "overlay_position"]


def load_config(path: str | None = None) -> AppConfig:
    """Load configuration from a JSON file, falling back to defaults.

    Keys from older versions (format modes, colours, ...) are ignored.
    """
    path = path or _default_config_path()
    config = AppConfig()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in _CONFIG_FIELDS:
            if key in data:
                setattr(config, key, data[key])
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    config.validate()
    return config


def save_config(config: AppConfig, path: str | None = None) -> None:
    """Save configuration to a JSON file. Raises OSError on failure."""
    path = path or _default_config_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=4)
```

Remove the now-unused `import re` from the top of the file. (`save_config` now raises instead of printing, so the bridge can report the error.)

- [ ] **Step 4: Run the config tests**

Run: `python -m pytest tests/test_config.py -q`
Expected: PASS. Other test files still fail on import; tasks 2-8 fix them.

- [ ] **Step 5: Commit**

```bash
git add shuper_whisper/config.py tests/test_config.py
git commit -m "refactor(config): drop format modes, colours and hold mode; store device by reference"
```

---

### Task 2: Text rules

**Files:**
- Create: `shuper_whisper/text_rules.py`
- Modify: `shuper_whisper/dictionary.py` (add `get_replacements`)
- Delete: `shuper_whisper/smart_text.py`, `tests/test_smart_text.py`
- Test: `tests/test_text_rules.py`, `tests/test_dictionary.py` (one new test)

**Interfaces:**
- Produces: `clean(text: str, replacements: Iterable[tuple[str, str]] = ()) -> str`
- Produces: `join(text: str, before: str | None) -> str`. `before` is the text before the caret: `""` for an empty field, `None` if unknown.
- Produces: `WordDictionary.get_replacements() -> list[tuple[str, str]]`, as `(heard, word)` pairs.

- [ ] **Step 1: Write `tests/test_text_rules.py`**

```python
"""Tests for deterministic dictation cleanup."""

import pytest

from shuper_whisper.text_rules import clean, join


class TestWhitespace:
    def test_collapses_double_spaces(self):
        assert clean("Hello  there.   How are you?") == "Hello there. How are you?"

    def test_strips_edges(self):
        assert clean("  Hello.  ") == "Hello."

    def test_no_space_before_punctuation(self):
        assert clean("Hello , world .") == "Hello, world."


class TestDashes:
    @pytest.mark.parametrize("raw", [
        "I went home — then I slept.",
        "I went home—then I slept.",
        "I went home – then I slept.",
        "I went home -- then I slept.",
        "I went home - then I slept.",
    ])
    def test_dashes_become_commas(self, raw):
        assert clean(raw) == "I went home, then I slept."

    def test_hyphenated_words_untouched(self):
        assert clean("A well-known follow-up.") == "A well-known follow-up."

    def test_trailing_dash_dropped(self):
        assert clean("I was going to —") == "I was going to"


class TestEllipses:
    def test_trailing_ellipsis_removed(self):
        assert clean("I went to the...") == "I went to the"

    def test_unicode_ellipsis_removed(self):
        assert clean("I went to the…") == "I went to the"

    def test_mid_ellipsis_before_lowercase_is_a_space(self):
        assert clean("I was thinking... maybe not.") == "I was thinking maybe not."

    def test_mid_ellipsis_before_capital_ends_sentence(self):
        assert clean("I was thinking... Maybe not.") == "I was thinking. Maybe not."


class TestFillers:
    def test_leading_filler(self):
        assert clean("Um, so we should go.") == "so we should go."

    def test_filler_between_commas(self):
        assert clean("I think, uh, we should go.") == "I think we should go."

    def test_filler_sentence(self):
        assert clean("Okay. Um. Next thing.") == "Okay. Next thing."

    def test_keeps_like_and_just(self):
        assert clean("I just like it.") == "I just like it."

    def test_does_not_eat_words_containing_fillers(self):
        assert clean("The umbrella is human.") == "The umbrella is human."


class TestCommands:
    def test_period(self):
        assert clean("send it today period") == "send it today."

    def test_comma(self):
        assert clean("hello comma world") == "hello, world"

    def test_question_mark(self):
        assert clean("are you coming question mark") == "are you coming?"

    def test_exclamation(self):
        assert clean("great exclamation point") == "great!"

    def test_colon(self):
        assert clean("note colon buy milk") == "note: buy milk"

    def test_whisper_punctuated_command(self):
        assert clean("Send it today, period.") == "Send it today."

    def test_new_line(self):
        assert clean("Dear Dana, new line thanks for the update.") == "Dear Dana,\nThanks for the update."

    def test_new_paragraph(self):
        assert clean("First point. New paragraph. Second point.") == "First point.\n\nSecond point."

    def test_capitalises_after_command_period(self):
        assert clean("done period next one") == "done. Next one"


class TestReplacements:
    def test_whole_word_case_insensitive(self):
        assert clean("I drove to mackinaw today.", [("mackinaw", "Mackinac")]) == "I drove to Mackinac today."

    def test_not_inside_other_words(self):
        assert clean("Mackinawville", [("mackinaw", "Mackinac")]) == "Mackinawville"

    def test_multi_word(self):
        assert clean("open shoe per whisper", [("shoe per whisper", "ShuperWhisper")]) == "open ShuperWhisper"

    def test_identity_pairs_ignored(self):
        assert clean("Dana", [("dana", "Dana")]) == "Dana"


class TestJoin:
    def test_unknown_context_capitalises_without_space(self):
        assert join("hello there.", None) == "Hello there."

    def test_empty_field(self):
        assert join("hello.", "") == "Hello."

    def test_after_newline(self):
        assert join("hello.", "Dear Dana,\n") == "Hello."

    def test_after_sentence_end(self):
        assert join("next thing.", "Done.") == " Next thing."

    def test_after_sentence_end_and_space(self):
        assert join("next thing.", "Done. ") == "Next thing."

    def test_mid_sentence_softens_common_starter(self):
        assert join("Then we left.", "We ate dinner") == " then we left."

    def test_mid_sentence_keeps_proper_noun(self):
        assert join("Dana left.", "We ate with") == " Dana left."

    def test_mid_sentence_keeps_i(self):
        assert join("I left.", "Then") == " I left."

    def test_after_opening_bracket(self):
        assert join("see below)", "(") == "see below)"

    def test_punctuation_attaches(self):
        assert join(", and then", "Hello") == ", and then"

    def test_leading_newline_untouched(self):
        assert join("\nThanks.", "Hi") == "\nThanks."

    def test_empty_text(self):
        assert join("", "Hello") == ""
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_text_rules.py -q`
Expected: FAIL with `ModuleNotFoundError: shuper_whisper.text_rules`.

- [ ] **Step 3: Create `shuper_whisper/text_rules.py`**

```python
"""Deterministic cleanup for dictated text.

No AI and no network. Every rule is a regex with a test, and the goal is text
that reads like a person typed it: single spaces, no em-dashes, no filler.

clean() tidies a transcription on its own; join() fits it onto whatever text
already precedes the caret.
"""

import re
from typing import Iterable

_PUNCT = ",.;:!?"
_PUNCT_CLASS = re.escape(_PUNCT)
_SENTENCE_END = ".!?"
_OPENERS = "([{\"'“‘"

# Spoken commands, longest phrase first.
_BREAK_COMMANDS = (("new paragraph", "\n\n"), ("new line", "\n"))
_PUNCT_COMMANDS = (
    ("question mark", "?"),
    ("exclamation point", "!"),
    ("exclamation mark", "!"),
    ("full stop", "."),
    ("period", "."),
    ("comma", ","),
    ("colon", ":"),
)

# um, umm, uh, uhh, erm, hmm -- optionally wrapped in a comma / followed by a period.
_FILLER_RE = re.compile(r",?\s*\b(?:u+m+|u+h+|e+r+m+|h+m+)\b[,.]?", re.IGNORECASE)
# Em dash, en dash, double hyphen, or a hyphen with spaces on both sides.
_DASH_RE = re.compile(r"\s*(?:—|–|--)\s*|\s+-\s+")
_TRAILING_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3,}|…)\s*$")
_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3,}|…)\s*")
_SENTENCE_START_RE = re.compile(r"([.!?]\s+|\n)([a-z])")

# Words Whisper capitalises at the start of every utterance that are almost
# never proper nouns -- lowercased when the utterance continues a sentence.
_LOWER_STARTERS = frozenset(
    "a an and as at but by for from if in into is it its of on or so than that "
    "the then there these they this those to was we were what when where which "
    "while who with you".split()
)


def _phrase_pattern(phrase: str) -> str:
    return r"\b" + r"\s*".join(re.escape(w) for w in phrase.split()) + r"\b"


def _apply_replacements(text: str, replacements: Iterable[tuple[str, str]]) -> str:
    for heard, word in replacements:
        heard = heard.strip()
        if not heard or heard.lower() == word.lower():
            continue
        pattern = rf"(?<![\w']){re.escape(heard)}(?![\w'])"
        text = re.sub(pattern, lambda _m, w=word: w, text, flags=re.IGNORECASE)
    return text


def _apply_commands(text: str) -> str:
    for phrase, mark in _BREAK_COMMANDS:
        text = re.sub(rf"\s*{_phrase_pattern(phrase)}[{_PUNCT_CLASS}]?\s*",
                      mark, text, flags=re.IGNORECASE)
    for phrase, mark in _PUNCT_COMMANDS:
        text = re.sub(rf"[{_PUNCT_CLASS}]?\s*{_phrase_pattern(phrase)}[{_PUNCT_CLASS}]?",
                      mark, text, flags=re.IGNORECASE)
    return text


def _ellipsis(match: re.Match) -> str:
    following = match.string[match.end():match.end() + 1]
    return " " if following.islower() else ". "


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(rf" +([{_PUNCT_CLASS}])", r"\1", text)
    text = re.sub(r",(?:\s*,)+", ",", text)
    text = re.sub(r",\s*([.;:!?])", r"\1", text)
    text = re.sub(r"([.;:!?]),", r"\1", text)
    text = re.sub(r"^[ ,]+", "", text)
    text = re.sub(r"[ ,]+$", "", text)
    return text


def clean(text: str, replacements: Iterable[tuple[str, str]] = ()) -> str:
    """Tidy one transcription: replacements, spoken commands, fillers, dashes,
    ellipses, spacing, and capitalisation after sentence ends."""
    text = _apply_replacements(text, replacements)
    text = _apply_commands(text)
    text = _FILLER_RE.sub("", text)
    text = _DASH_RE.sub(", ", text)
    text = _TRAILING_ELLIPSIS_RE.sub("", text)
    text = _ELLIPSIS_RE.sub(_ellipsis, text)
    text = _tidy(text)
    return _SENTENCE_START_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)


def _capitalise(text: str) -> str:
    return text[:1].upper() + text[1:]


def _soften(text: str) -> str:
    match = re.match(r"([A-Z][a-z']*)\b", text)
    if match and match.group(1).lower() in _LOWER_STARTERS:
        return text[:1].lower() + text[1:]
    return text


def join(text: str, before: str | None) -> str:
    """Fit cleaned ``text`` onto the text before the caret.

    ``before`` is what precedes the caret (only its tail matters), "" for an
    empty field, or None when it couldn't be read -- then we assume a fresh
    sentence and add no leading space.
    """
    if not text or text[0] == "\n":
        return text
    if before is None:
        return _capitalise(text)
    tail = before.rstrip(" \t")
    if tail == "" or tail[-1] in "\r\n":
        return _capitalise(text)
    if before[-1] in " \t" or before[-1] in _OPENERS or text[0] in _PUNCT:
        prefix = ""
    else:
        prefix = " "
    if tail[-1] in _SENTENCE_END:
        return prefix + _capitalise(text)
    return prefix + _soften(text)
```

- [ ] **Step 4: Run the text-rule tests**

Run: `python -m pytest tests/test_text_rules.py -q`
Expected: PASS. If a case fails, fix the regex, not the test. Each test states the behaviour the spec asks for.

- [ ] **Step 5: Add `get_replacements` to the dictionary (test first)**

Append to `tests/test_dictionary.py`:

```python
def test_get_replacements_maps_hint_to_word(tmp_path):
    from shuper_whisper.dictionary import WordDictionary
    d = WordDictionary(path=str(tmp_path / "d.json"))
    d.add("Mackinac", "mackinaw")
    d.add("Dana")
    assert d.get_replacements() == [("mackinaw", "Mackinac")]
```

Run: `python -m pytest tests/test_dictionary.py -q -k replacements`. It fails with AttributeError.

Add this to `WordDictionary` in `shuper_whisper/dictionary.py`:

```python
    def get_replacements(self) -> list[tuple[str, str]]:
        """(heard, word) pairs: a phonetic hint is what Whisper hears for the word."""
        return [(e.phonetic, e.word) for e in self._entries if e.phonetic]
```

Run it again. It passes.

- [ ] **Step 6: Delete the old smart-text module**

```bash
git rm shuper_whisper/smart_text.py tests/test_smart_text.py
```

- [ ] **Step 7: Commit**

```bash
git add shuper_whisper/text_rules.py shuper_whisper/dictionary.py tests/test_text_rules.py tests/test_dictionary.py
git commit -m "feat(text): deterministic cleanup rules replace smart_text and the AI formatter"
```

---

### Task 3: Device discovery and resolution

**Files:**
- Create: `shuper_whisper/audio_devices.py`
- Test: `tests/test_audio_devices.py`

**Interfaces:**
- Produces: `InputDevice(index, name, hostapi, channels, samplerate, is_default)`, with `.ref() -> dict` and `.to_dict() -> dict` (which adds `hostapi_label`).
- Produces: `refresh() -> None`
- Produces: `list_input_devices(devices=None, hostapis=None) -> list[InputDevice]`
- Produces: `default_input_index(devices=None, hostapis=None) -> int | None`
- Produces: `resolve(ref, devices=None, hostapis=None) -> int`. Raises `DeviceNotFoundError`.
- Produces: `migrate(value, devices=None, hostapis=None) -> dict | None`
- Produces: `check(ref) -> str | None`. Returns an error message, or None if the device opens.

- [ ] **Step 1: Write `tests/test_audio_devices.py`**

```python
"""Tests for device listing, de-duplication, resolution and migration."""

import pytest

from shuper_whisper import audio_devices as ad

HOSTAPIS = [
    {"name": "MME", "default_input_device": 1},
    {"name": "Windows DirectSound", "default_input_device": 4},
    {"name": "Windows WASAPI", "default_input_device": 7},
    {"name": "Windows WDM-KS", "default_input_device": -1},
]


def dev(name, hostapi, ins=2, rate=48000.0):
    return {"name": name, "hostapi": hostapi, "max_input_channels": ins,
            "default_samplerate": rate}


B1 = "Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO)"
MIC = "Microphone (Realtek(R) Audio)"
DEVICES = [
    dev("Microsoft Sound Mapper - Input", 0),          # 0 pseudo
    dev(MIC, 0, rate=44100.0),                         # 1 MME
    dev(B1[:31], 0, rate=44100.0),                     # 2 MME, truncated
    dev("Speakers (Realtek(R) Audio)", 0, ins=0),      # 3 output only
    dev(MIC, 1),                                       # 4 DirectSound
    dev(B1, 1),                                        # 5 DirectSound
    dev("Primary Sound Capture Driver", 1),            # 6 pseudo
    dev(MIC, 2),                                       # 7 WASAPI (default)
    dev(B1, 2),                                        # 8 WASAPI
    dev("Voicemeeter Point 1", 3),                     # 9 WDM-KS
    dev("Old USB Mic", 0, rate=44100.0),               # 10 MME only
]


def listing():
    return ad.list_input_devices(DEVICES, HOSTAPIS)


class TestList:
    def test_one_entry_per_device_preferring_wasapi(self):
        got = {(d.name, d.hostapi) for d in listing()}
        assert got == {(MIC, "Windows WASAPI"), (B1, "Windows WASAPI"), ("Old USB Mic", "MME")}

    def test_drops_wdmks_and_pseudo_devices(self):
        names = [d.name for d in listing()]
        assert "Voicemeeter Point 1" not in names
        assert "Microsoft Sound Mapper - Input" not in names

    def test_default_marked(self):
        defaults = [d.name for d in listing() if d.is_default]
        assert defaults == [MIC]

    def test_to_dict_has_label(self):
        d = next(d for d in listing() if d.name == B1).to_dict()
        assert d["hostapi_label"] == "WASAPI"
        assert d["index"] == 8


class TestResolve:
    def test_none_is_wasapi_default(self):
        assert ad.resolve(None, DEVICES, HOSTAPIS) == 7

    def test_exact_ref(self):
        assert ad.resolve({"name": B1, "hostapi": "Windows DirectSound"}, DEVICES, HOSTAPIS) == 5

    def test_name_only_prefers_wasapi(self):
        assert ad.resolve({"name": B1, "hostapi": None}, DEVICES, HOSTAPIS) == 8

    def test_hostapi_gone_falls_back_to_same_name(self):
        assert ad.resolve({"name": "Old USB Mic", "hostapi": "Windows WASAPI"}, DEVICES, HOSTAPIS) == 10

    def test_truncated_mme_name_matches(self):
        assert ad.resolve({"name": B1[:31], "hostapi": "MME"}, DEVICES, HOSTAPIS) == 2

    def test_missing_device_raises(self):
        with pytest.raises(ad.DeviceNotFoundError, match="Ghost Mic"):
            ad.resolve({"name": "Ghost Mic", "hostapi": None}, DEVICES, HOSTAPIS)


class TestMigrate:
    def test_int_becomes_ref(self):
        assert ad.migrate(8, DEVICES, HOSTAPIS) == {"name": B1, "hostapi": "Windows WASAPI"}

    def test_wdmks_index_becomes_name_only(self):
        assert ad.migrate(9, DEVICES, HOSTAPIS) == {"name": "Voicemeeter Point 1", "hostapi": None}

    def test_out_of_range_becomes_default(self):
        assert ad.migrate(99, DEVICES, HOSTAPIS) is None

    def test_non_int_passes_through(self):
        ref = {"name": B1, "hostapi": None}
        assert ad.migrate(ref, DEVICES, HOSTAPIS) is ref
        assert ad.migrate(None, DEVICES, HOSTAPIS) is None
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_audio_devices.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `shuper_whisper/audio_devices.py`**

```python
"""Input-device discovery and resolution.

PortAudio lists each physical device once per Windows host API (MME,
DirectSound, WASAPI, WDM-KS) and renumbers devices whenever one appears or
disappears -- e.g. when Voicemeeter restarts. So config stores a device by name
and host API, and this module turns that reference into a current index.
"""

from dataclasses import asdict, dataclass, replace

import sounddevice as sd

HOSTAPI_PREFERENCE = ("Windows WASAPI", "MME", "Windows DirectSound")
HOSTAPI_LABELS = {"Windows WASAPI": "WASAPI", "MME": "MME", "Windows DirectSound": "DirectSound"}
_MME_NAME_LIMIT = 31  # MME truncates device names to 31 characters
_PSEUDO_DEVICES = ("Microsoft Sound Mapper - Input", "Primary Sound Capture Driver")
_RANK = {api: i for i, api in enumerate(HOSTAPI_PREFERENCE)}


class DeviceNotFoundError(RuntimeError):
    """The configured input device isn't connected right now."""


@dataclass(frozen=True)
class InputDevice:
    index: int
    name: str
    hostapi: str
    channels: int
    samplerate: float
    is_default: bool = False

    def ref(self) -> dict:
        return {"name": self.name, "hostapi": self.hostapi}

    def to_dict(self) -> dict:
        data = asdict(self)
        data["hostapi_label"] = HOSTAPI_LABELS.get(self.hostapi, self.hostapi)
        return data


def refresh() -> None:
    """Re-scan devices. PortAudio otherwise caches the list from startup."""
    sd._terminate()
    sd._initialize()


def _inputs(devices=None, hostapis=None) -> list[InputDevice]:
    devices = sd.query_devices() if devices is None else devices
    hostapis = sd.query_hostapis() if hostapis is None else hostapis
    found = []
    for index, d in enumerate(devices):
        api = hostapis[d["hostapi"]]["name"]
        if d["max_input_channels"] <= 0 or api not in _RANK or d["name"] in _PSEUDO_DEVICES:
            continue
        found.append(InputDevice(index, d["name"], api, int(d["max_input_channels"]),
                                 float(d["default_samplerate"])))
    return found


def default_input_index(devices=None, hostapis=None) -> int | None:
    """WASAPI's default input (its native-rate handling is the most reliable),
    else PortAudio's overall default."""
    hostapis = sd.query_hostapis() if hostapis is None else hostapis
    for api in hostapis:
        if api["name"] == "Windows WASAPI" and api.get("default_input_device", -1) >= 0:
            return api["default_input_device"]
    index = sd.default.device[0]
    return index if index is not None and index >= 0 else None


def list_input_devices(devices=None, hostapis=None) -> list[InputDevice]:
    """One entry per physical input, from the most preferred host API."""
    inputs = _inputs(devices, hostapis)
    default_index = default_input_index(devices, hostapis)
    default_key = next((d.name[:_MME_NAME_LIMIT] for d in inputs if d.index == default_index), None)

    groups: dict[str, list[InputDevice]] = {}
    for d in inputs:
        groups.setdefault(d.name[:_MME_NAME_LIMIT], []).append(d)

    result = []
    for key, group in groups.items():
        best = min(_RANK[d.hostapi] for d in group)
        for d in group:
            if _RANK[d.hostapi] == best:
                result.append(replace(d, is_default=(key == default_key)))
    return sorted(result, key=lambda d: d.name.lower())


def resolve(ref, devices=None, hostapis=None) -> int:
    """Current PortAudio index for a stored reference (None = system default)."""
    if ref is None:
        index = default_input_index(devices, hostapis)
        if index is None:
            raise DeviceNotFoundError("No microphone found")
        return index
    if isinstance(ref, int):
        return ref
    name, hostapi = ref["name"], ref.get("hostapi")
    inputs = _inputs(devices, hostapis)
    for matches in (
        [d for d in inputs if d.name == name and d.hostapi == hostapi],
        [d for d in inputs if d.name == name],
        [d for d in inputs if d.name[:_MME_NAME_LIMIT] == name[:_MME_NAME_LIMIT]],
    ):
        if matches:
            return min(matches, key=lambda d: _RANK[d.hostapi]).index
    raise DeviceNotFoundError(f"{name} isn't connected")


def migrate(value, devices=None, hostapis=None):
    """Turn a legacy int index into a reference; anything else passes through."""
    if not isinstance(value, int) or isinstance(value, bool):
        return value
    for d in _inputs(devices, hostapis):
        if d.index == value:
            return d.ref()
    devices = sd.query_devices() if devices is None else devices
    if 0 <= value < len(devices) and devices[value]["max_input_channels"] > 0:
        return {"name": devices[value]["name"], "hostapi": None}
    return None


def check(ref) -> str | None:
    """Try the device at its native rate. Returns an error message or None."""
    try:
        index = resolve(ref)
        info = sd.query_devices(index, "input")
        sd.check_input_settings(
            device=index,
            channels=max(1, min(int(info["max_input_channels"]), 2)),
            samplerate=info["default_samplerate"],
            dtype="float32",
        )
        return None
    except Exception as e:  # PortAudioError, DeviceNotFoundError, ValueError
        return str(e)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_audio_devices.py -q`
Expected: PASS.

- [ ] **Step 5: Check against the real devices**

```bash
python -c "from shuper_whisper import audio_devices as ad; [print(d.index, d.hostapi, d.name, d.is_default) for d in ad.list_input_devices()]; print(ad.check({'name':'Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO)','hostapi':'Windows WASAPI'}))"
```

Expected:
- Voicemeeter Out B1 is listed once, under WASAPI.
- `check(...)` prints `None`, because the native 48 kHz rate is accepted.

- [ ] **Step 6: Commit**

```bash
git add shuper_whisper/audio_devices.py tests/test_audio_devices.py
git commit -m "feat(audio): resolve input devices by name and host API, dedupe the list"
```

---

### Task 4: Audio capture at native rate

**Files:**
- Modify: `shuper_whisper/audio.py` (rewrite)
- Test: `tests/test_audio.py` (rewrite)

**Interfaces:**
- Consumes: `audio_devices.resolve(ref) -> int`
- Produces: `AudioRecorder(device_ref=None, stream_factory=None, resolver=None)`
- Produces: `start_recording()`. It opens the stream and raises on failure.
- Produces: `stop_recording() -> np.ndarray | None`. It closes the stream and returns float32 audio at 16 kHz.
- Produces: `get_levels(count) -> list[float]`, `is_recording`, `stream_error: str | None`, and `TARGET_RATE = 16000`.
- Removed: `open_stream`, `close_stream`, `list_devices`, `get_default_device_name`.

- [ ] **Step 1: Rewrite `tests/test_audio.py`**

```python
"""Tests for AudioRecorder: native-rate open, resampling, WASAPI fallback."""

import numpy as np
import pytest
import sounddevice as sd

from shuper_whisper import audio as audio_mod
from shuper_whisper.audio import AudioRecorder


class FakeStream:
    def __init__(self, fail=False, **kwargs):
        if fail:
            raise sd.PortAudioError("Invalid sample rate", -9997)
        self.kwargs = kwargs
        self.started = self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        pass

    def close(self):
        self.closed = True

    def feed(self, block):
        self.kwargs["callback"](block, len(block), None, sd.CallbackFlags())


@pytest.fixture
def device_info(monkeypatch):
    info = {"max_input_channels": 2, "default_samplerate": 48000.0, "hostapi": 2}
    monkeypatch.setattr(audio_mod.sd, "query_devices", lambda *a, **k: info)
    monkeypatch.setattr(audio_mod.sd, "query_hostapis",
                        lambda i=None: {"name": "Windows WASAPI"})
    return info


def make(streams, fail_first=False):
    calls = {"n": 0}

    def factory(**kwargs):
        calls["n"] += 1
        s = FakeStream(fail=fail_first and calls["n"] == 1, **kwargs)
        streams.append(s)
        return s
    return AudioRecorder(device_ref=None, stream_factory=factory, resolver=lambda ref: 8)


def sine(rate, seconds, channels=2):
    t = np.arange(int(rate * seconds)) / rate
    mono = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    return np.repeat(mono[:, None], channels, axis=1)


class TestOpen:
    def test_opens_at_native_rate_with_device_index(self, device_info):
        streams = []
        r = make(streams)
        r.start_recording()
        kw = streams[0].kwargs
        assert kw["samplerate"] == 48000 and kw["device"] == 8 and kw["channels"] == 2
        assert streams[0].started and r.is_recording

    def test_wasapi_fallback_uses_auto_convert(self, device_info):
        streams = []
        r = make(streams, fail_first=True)
        r.start_recording()
        kw = streams[-1].kwargs
        assert kw["samplerate"] == 16000
        assert kw["extra_settings"] is not None

    def test_non_wasapi_failure_raises(self, device_info, monkeypatch):
        monkeypatch.setattr(audio_mod.sd, "query_hostapis", lambda i=None: {"name": "MME"})
        r = make([], fail_first=True)
        with pytest.raises(sd.PortAudioError):
            r.start_recording()
        assert not r.is_recording


class TestCapture:
    def test_resamples_48k_stereo_to_16k_mono(self, device_info):
        streams = []
        r = make(streams)
        r.start_recording()
        block = sine(48000, 1.0)
        for i in range(0, len(block), 1440):
            streams[0].feed(block[i:i + 1440])
        audio = r.stop_recording()
        assert audio.dtype == np.float32 and audio.ndim == 1
        assert abs(len(audio) - 16000) < 400
        assert 0.15 < float(np.sqrt(np.mean(audio ** 2))) < 0.25
        assert streams[0].closed

    def test_stop_without_audio_returns_none(self, device_info):
        r = make([])
        r.start_recording()
        assert r.stop_recording() is None

    def test_levels(self, device_info):
        streams = []
        r = make(streams)
        assert r.get_levels(5) == [0.0] * 5
        r.start_recording()
        streams[0].feed(sine(48000, 0.03))
        assert r.get_levels(5)[-1] > 0

    def test_unexpected_stream_end_sets_error(self, device_info):
        streams = []
        r = make(streams)
        r.start_recording()
        streams[0].kwargs["finished_callback"]()
        assert r.stream_error
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_audio.py -q`
Expected: FAIL (`AudioRecorder` has no `device_ref` / `stream_factory` parameters).

- [ ] **Step 3: Rewrite `shuper_whisper/audio.py`**

```python
"""Microphone capture: open at the device's native rate, deliver 16 kHz mono.

The stream is opened when dictation starts and closed when it stops, so the
Windows mic-in-use indicator is only lit while you're dictating.
"""

import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
import soxr

from . import audio_devices


class AudioRecorder:
    TARGET_RATE = 16000
    BLOCK_SECONDS = 0.03
    _LEVEL_HISTORY = 60

    def __init__(self, device_ref=None, stream_factory: Optional[Callable] = None,
                 resolver: Optional[Callable] = None):
        self._device_ref = device_ref
        self._stream_factory = stream_factory or sd.InputStream
        self._resolver = resolver or audio_devices.resolve
        self._stream = None
        self._resampler: Optional[soxr.ResampleStream] = None
        self._recording = False
        self._stopping = False
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._levels: list[float] = []
        self._level_lock = threading.Lock()
        self.stream_error: Optional[str] = None

    # -- stream callbacks (PortAudio thread) ---------------------------------

    def _callback(self, indata, frames, time_info, status) -> None:
        mono = indata.mean(axis=1) if indata.shape[1] > 1 else indata[:, 0]
        mono = np.ascontiguousarray(mono, dtype=np.float32)
        if self._resampler is not None:
            mono = self._resampler.resample_chunk(mono)
        if len(mono):
            with self._lock:
                if self._recording:
                    self._chunks.append(mono.copy())
            level = float(np.sqrt(np.mean(mono ** 2)))
            with self._level_lock:
                self._levels.append(level)
                del self._levels[:-self._LEVEL_HISTORY]

    def _on_finished(self) -> None:
        if self._recording and not self._stopping:
            self.stream_error = "The microphone stopped unexpectedly"

    # -- open / close ----------------------------------------------------------

    def _open(self, index: int):
        info = sd.query_devices(index, "input")
        channels = max(1, min(int(info["max_input_channels"]), 2))
        native = int(info["default_samplerate"])
        common = dict(device=index, channels=channels, dtype="float32",
                      callback=self._callback, finished_callback=self._on_finished)
        try:
            stream = self._stream_factory(samplerate=native,
                                          blocksize=int(native * self.BLOCK_SECONDS), **common)
            rate = native
        except sd.PortAudioError:
            if "WASAPI" not in sd.query_hostapis(info["hostapi"])["name"]:
                raise
            stream = self._stream_factory(
                samplerate=self.TARGET_RATE,
                blocksize=int(self.TARGET_RATE * self.BLOCK_SECONDS),
                extra_settings=sd.WasapiSettings(auto_convert=True), **common)
            rate = self.TARGET_RATE
        self._resampler = (soxr.ResampleStream(rate, self.TARGET_RATE, 1, dtype="float32")
                           if rate != self.TARGET_RATE else None)
        return stream

    def start_recording(self) -> None:
        """Open the configured device and start capturing. Raises on failure."""
        with self._lock:
            self._chunks = []
        with self._level_lock:
            self._levels.clear()
        self.stream_error = None
        self._stopping = False
        try:
            index = self._resolver(self._device_ref)
        except audio_devices.DeviceNotFoundError:
            audio_devices.refresh()  # it may have appeared since PortAudio last scanned
            index = self._resolver(self._device_ref)
        stream = self._open(index)
        self._stream = stream
        self._recording = True
        try:
            stream.start()
        except Exception:
            self._recording = False
            self._stream = None
            stream.close()
            raise

    def stop_recording(self) -> Optional[np.ndarray]:
        """Close the stream and return everything captured as 16 kHz float32."""
        self._stopping = True
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
        with self._lock:
            self._recording = False
            if self._resampler is not None:
                tail = self._resampler.resample_chunk(np.zeros(0, np.float32), last=True)
                if len(tail):
                    self._chunks.append(tail)
            chunks, self._chunks = self._chunks, []
        self._resampler = None
        if not chunks:
            return None
        return np.concatenate(chunks).astype(np.float32)

    # -- levels -----------------------------------------------------------------

    def get_levels(self, count: int = 30) -> list[float]:
        with self._level_lock:
            history = list(self._levels)
        if len(history) >= count:
            return history[-count:]
        return [0.0] * (count - len(history)) + history

    @property
    def is_recording(self) -> bool:
        return self._recording
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_audio.py -q`
Expected: PASS.

- [ ] **Step 5: Live check on B1**

```bash
python -c "
import time; from shuper_whisper.audio import AudioRecorder
r=AudioRecorder({'name':'Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO)','hostapi':'Windows WASAPI'})
r.start_recording(); time.sleep(2); a=r.stop_recording(); print(len(a), float((a**2).mean()**0.5))"
```

Expected: about 32000 samples, and a nonzero RMS if you spoke during the two seconds.

- [ ] **Step 6: Commit**

```bash
git add shuper_whisper/audio.py tests/test_audio.py
git commit -m "fix(audio): open devices at native rate and resample, so WASAPI-only buses like Voicemeeter B1 work"
```

---

### Task 5: Transcriber on the GPU, with clean joins

**Files:**
- Modify: `shuper_whisper/transcriber.py`
- Test: `tests/test_transcriber.py` (new)

**Interfaces:**
- Produces: `select_compute() -> tuple[str, str]`, either `("cuda", "float16")` or `("cpu", "int8")`.
- Produces: `resolve_model_size(model_size: str, device: str) -> str`
- Produces: `Transcriber(model_size="auto", language="en", device=None, compute_type=None)`. It has `.load_model()`, `.transcribe(audio, initial_prompt=None, hotwords=None) -> str`, `.device`, `.model_size` (resolved after load), `.loaded` and `.language` (settable).

- [ ] **Step 1: Write `tests/test_transcriber.py`**

```python
"""Tests for transcriber compute selection and segment joining."""

from types import SimpleNamespace

import numpy as np

from shuper_whisper import transcriber as tr


class FakeModel:
    def __init__(self, texts):
        self.texts = texts
        self.kwargs = None

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        return iter(SimpleNamespace(text=t) for t in self.texts), None


def loaded(texts, language="en"):
    t = tr.Transcriber(model_size="base", language=language, device="cpu", compute_type="int8")
    t._model = FakeModel(texts)
    return t


def test_joins_segments_with_single_spaces():
    t = loaded([" Hello there.", " How are you?", "  "])
    assert t.transcribe(np.zeros(16000, np.float32)) == "Hello there. How are you?"


def test_vad_and_language_passed():
    t = loaded([" Hi."], language="auto")
    t.transcribe(np.zeros(16000, np.float32), initial_prompt="Vocabulary: Dana.", hotwords="Dana")
    kw = t._model.kwargs
    assert kw["vad_filter"] is True
    assert kw["language"] is None
    assert kw["initial_prompt"] == "Vocabulary: Dana."
    assert kw["hotwords"] == "Dana"
    assert kw["condition_on_previous_text"] is False


def test_auto_model_size():
    assert tr.resolve_model_size("auto", "cuda") == "large-v3-turbo"
    assert tr.resolve_model_size("auto", "cpu") == "base"
    assert tr.resolve_model_size("small", "cuda") == "small"


def test_select_compute_env_override(monkeypatch):
    monkeypatch.setenv("SHUPER_WHISPER_DEVICE", "cpu")
    assert tr.select_compute() == ("cpu", "int8")


def test_select_compute_falls_back_when_dlls_missing(monkeypatch):
    monkeypatch.delenv("SHUPER_WHISPER_DEVICE", raising=False)
    monkeypatch.setattr(tr, "_cuda_device_count", lambda: 1)
    monkeypatch.setattr(tr, "_load_cuda_dlls", lambda: False)
    assert tr.select_compute() == ("cpu", "int8")


def test_select_compute_uses_gpu_when_available(monkeypatch):
    monkeypatch.delenv("SHUPER_WHISPER_DEVICE", raising=False)
    monkeypatch.setattr(tr, "_cuda_device_count", lambda: 1)
    monkeypatch.setattr(tr, "_load_cuda_dlls", lambda: True)
    assert tr.select_compute() == ("cuda", "float16")
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_transcriber.py -q`
Expected: FAIL (no `select_compute`, `resolve_model_size`).

- [ ] **Step 3: Rewrite `shuper_whisper/transcriber.py`**

Keep `_bundled_model_path` as it is. Replace the rest of the file with:

```python
import ctypes
import os
import sys
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

# ctranslate2 >= 4.5 is built against CUDA 12 + cuDNN 9.
_CUDA_DLLS = ("cublas64_12.dll", "cudnn64_9.dll")


def _cuda_device_count() -> int:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def _nvidia_dll_dirs() -> list[str]:
    """bin/ folders of the nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheels."""
    roots = []
    try:
        import nvidia  # namespace package installed by the wheels
        roots.extend(nvidia.__path__)
    except ImportError:
        pass
    if getattr(sys, "frozen", False):
        roots.append(os.path.join(sys._MEIPASS, "nvidia"))
    dirs = []
    for root in roots:
        for lib in ("cublas", "cudnn"):
            path = os.path.join(root, lib, "bin")
            if os.path.isdir(path):
                dirs.append(path)
    return dirs


def _load_cuda_dlls() -> bool:
    """Make the CUDA runtime findable and prove it loads.

    ctranslate2 aborts the whole process (no exception) when it can't find
    cuDNN mid-inference, so this must succeed before we ever pick "cuda".
    """
    for path in _nvidia_dll_dirs():
        os.add_dll_directory(path)
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
    try:
        for dll in _CUDA_DLLS:
            ctypes.WinDLL(dll)
        return True
    except OSError:
        return False


def select_compute() -> tuple[str, str]:
    """("cuda", "float16") when a usable NVIDIA GPU is present, else CPU int8.

    Set SHUPER_WHISPER_DEVICE=cpu to force CPU.
    """
    if os.environ.get("SHUPER_WHISPER_DEVICE", "").lower() == "cpu":
        return ("cpu", "int8")
    if _cuda_device_count() > 0 and _load_cuda_dlls():
        return ("cuda", "float16")
    return ("cpu", "int8")


def resolve_model_size(model_size: str, device: str) -> str:
    if model_size != "auto":
        return model_size
    return "large-v3-turbo" if device == "cuda" else "base"


class Transcriber:
    """Wraps faster-whisper's WhisperModel."""

    def __init__(self, model_size: str = "auto", language: str = "en",
                 device: Optional[str] = None, compute_type: Optional[str] = None):
        self._requested_size = model_size
        self._model_size = model_size
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._model: Optional[WhisperModel] = None

    def load_model(self) -> None:
        if self._device is None:
            self._device, self._compute_type = select_compute()
        self._model_size = resolve_model_size(self._requested_size, self._device)
        source = _bundled_model_path(self._model_size) or self._model_size
        print(f"Loading Whisper {self._model_size} on {self._device} ({self._compute_type})")
        self._model = WhisperModel(source, device=self._device, compute_type=self._compute_type)

    def transcribe(self, audio: np.ndarray, initial_prompt: Optional[str] = None,
                   hotwords: Optional[str] = None) -> str:
        """Transcribe 16 kHz mono float32 audio. Returns "" when nothing was said."""
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        kwargs = {
            "beam_size": 5,
            "language": None if self._language == "auto" else self._language,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 500},
            "condition_on_previous_text": False,
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        if hotwords:
            kwargs["hotwords"] = hotwords
        segments, _info = self._model.transcribe(audio, **kwargs)
        # Segment texts carry their own leading space; strip and re-join so
        # boundaries get exactly one.
        return " ".join(t for t in (s.text.strip() for s in segments) if t)

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def device(self) -> Optional[str]:
        return self._device

    @property
    def model_size(self) -> str:
        return self._model_size

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, value: str) -> None:
        self._language = value
```

Leave the module docstring and the imports already used by `_bundled_model_path` in place. The import list above replaces the old one.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_transcriber.py -q`
Expected: PASS.

- [ ] **Step 5: Real GPU check**

```bash
python -c "
import numpy as np, time
from shuper_whisper.transcriber import Transcriber, select_compute
print(select_compute())
t=Transcriber('tiny'); t.load_model(); s=time.time(); print(repr(t.transcribe(np.zeros(32000,np.float32))), t.device, round(time.time()-s,2))"
```

Expected: `('cuda', 'float16')`, then `'' cuda <seconds>`, and the process does not crash.
- If the output is `cpu`, check that `nvidia-cudnn-cu12` 9.x and `nvidia-cublas-cu12` are installed and that `python -m pip show ctranslate2` reports ≥ 4.5.
- The app still works on CPU either way.

- [ ] **Step 6: Commit**

```bash
git add shuper_whisper/transcriber.py tests/test_transcriber.py
git commit -m "feat(transcriber): use the GPU when CUDA loads, VAD on, single-space segment joins"
```

---

### Task 6: Typing at the caret (SendInput + UI Automation)

**Files:**
- Modify: `shuper_whisper/_win32_keys.py` (add SendInput)
- Create: `shuper_whisper/uia.py`
- Modify: `shuper_whisper/injector.py` (rewrite)
- Test: `tests/test_win32_input.py`, `tests/test_injector.py`

**Interfaces:**
- Produces in `_win32_keys`: `INPUT`, `text_to_inputs(text, backspaces=0) -> list[INPUT]`, `send_text(text, backspaces=0) -> None` (raises `InjectionBlocked`), `wait_for_modifiers_released(timeout=1.0) -> bool`, and `SHUPER_INPUT_TAG`.
- Produces in `uia`: `text_before_caret(timeout=0.3) -> str | None` and `focused_element_id(timeout=0.3) -> tuple | None`.
- Produces: `TextInjector(send=..., read_context=..., foreground=..., wait_modifiers=...)`, with `.context() -> str | None` and `.inject(text) -> str` (returns what was typed).

- [ ] **Step 1: Write `tests/test_win32_input.py`**

```python
"""Tests for SendInput event construction (no keystrokes are sent)."""

import ctypes

from shuper_whisper import _win32_keys as k


def test_input_struct_size_matches_windows_x64():
    assert ctypes.sizeof(k.INPUT) == 40


def test_ascii_char_is_unicode_down_up():
    events = k.text_to_inputs("a")
    assert len(events) == 2
    down, up = (e.union.ki for e in events)
    assert down.wScan == ord("a") and down.dwFlags == k.KEYEVENTF_UNICODE
    assert up.dwFlags == k.KEYEVENTF_UNICODE | k.KEYEVENTF_KEYUP
    assert down.dwExtraInfo == k.SHUPER_INPUT_TAG


def test_newline_is_enter_and_cr_skipped():
    events = k.text_to_inputs("\r\n")
    assert [e.union.ki.wVk for e in events] == [k.VK_RETURN, k.VK_RETURN]


def test_astral_char_is_surrogate_pair():
    events = k.text_to_inputs("😀")
    assert [e.union.ki.wScan for e in events[::2]] == [0xD83D, 0xDE00]


def test_backspaces_come_first():
    events = k.text_to_inputs("x", backspaces=2)
    assert [e.union.ki.wVk for e in events[:4]] == [k.VK_BACK] * 4
    assert events[4].union.ki.wScan == ord("x")
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_win32_input.py -q`
Expected: FAIL (no `INPUT`).

- [ ] **Step 3: Add SendInput to `shuper_whisper/_win32_keys.py`**

Delete `send_combo` and the `VK_HOME`, `VK_RIGHT`, `VK_C` and `VK_V` constants at the bottom; only the old injector used them. Add `import time` at the top. Then append:

```python
# --- SendInput ---------------------------------------------------------------

INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
VK_BACK = 0x08
VK_RETURN = 0x0D
# Stamped into dwExtraInfo so our own keystrokes can be told apart from the user's.
SHUPER_INPUT_TAG = 0x53575057


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.wintypes.WORD), ("wScan", ctypes.wintypes.WORD),
                ("dwFlags", ctypes.wintypes.DWORD), ("time", ctypes.wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.wintypes.LONG), ("dy", ctypes.wintypes.LONG),
                ("mouseData", ctypes.wintypes.DWORD), ("dwFlags", ctypes.wintypes.DWORD),
                ("time", ctypes.wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.wintypes.DWORD), ("wParamL", ctypes.wintypes.WORD),
                ("wParamH", ctypes.wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.wintypes.DWORD), ("union", _INPUTUNION)]


user32.SendInput.argtypes = (ctypes.wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = ctypes.wintypes.UINT


class InjectionBlocked(RuntimeError):
    """Windows refused our keystrokes (usually an elevated target window)."""


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=KEYBDINPUT(
        wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=SHUPER_INPUT_TAG)))


def text_to_inputs(text: str, backspaces: int = 0) -> list[INPUT]:
    events: list[INPUT] = []
    for _ in range(backspaces):
        events += [_key(vk=VK_BACK), _key(vk=VK_BACK, flags=KEYEVENTF_KEYUP)]
    for ch in text:
        if ch == "\r":
            continue
        if ch == "\n":
            events += [_key(vk=VK_RETURN), _key(vk=VK_RETURN, flags=KEYEVENTF_KEYUP)]
            continue
        data = ch.encode("utf-16-le")
        for i in range(0, len(data), 2):
            unit = int.from_bytes(data[i:i + 2], "little")
            events += [_key(scan=unit, flags=KEYEVENTF_UNICODE),
                       _key(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    return events


kernel32 = ctypes.windll.kernel32
advapi32 = ctypes.windll.advapi32
kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
kernel32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
advapi32.OpenProcessToken.argtypes = (ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD,
                                      ctypes.POINTER(ctypes.wintypes.HANDLE))
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TOKEN_QUERY = 0x0008
_TOKEN_ELEVATION = 20


def _is_elevated(process) -> bool:
    token = ctypes.wintypes.HANDLE()
    if not advapi32.OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(token)):
        return False
    try:
        elevation, size = ctypes.wintypes.DWORD(), ctypes.wintypes.DWORD()
        ok = advapi32.GetTokenInformation(token, _TOKEN_ELEVATION, ctypes.byref(elevation),
                                          ctypes.sizeof(elevation), ctypes.byref(size))
        return bool(ok and elevation.value)
    finally:
        kernel32.CloseHandle(token)


def foreground_blocks_input() -> bool:
    """True when the foreground app is elevated and we aren't: UIPI then drops
    our keystrokes, and SendInput doesn't reliably say so."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not process:
        return False  # can't tell; try anyway
    try:
        target_elevated = _is_elevated(process)
    finally:
        kernel32.CloseHandle(process)
    return target_elevated and not _is_elevated(kernel32.GetCurrentProcess())


def send_text(text: str, backspaces: int = 0) -> None:
    """Type ``text`` (after ``backspaces``) into the focused control in one
    SendInput call, so the user's own keystrokes can't interleave."""
    events = text_to_inputs(text, backspaces)
    if not events:
        return
    if foreground_blocks_input():
        raise InjectionBlocked("Can't type into admin windows unless ShuperWhisper runs as admin")
    array = (INPUT * len(events))(*events)
    if user32.SendInput(len(events), array, ctypes.sizeof(INPUT)) != len(events):
        raise InjectionBlocked("Windows blocked typing into this window (is it running as admin?)")


_MODIFIER_VKS = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # Shift, Ctrl, Alt, LWin, RWin


def wait_for_modifiers_released(timeout: float = 1.0) -> bool:
    """Wait until no modifier is physically held, so typed text isn't read as
    shortcuts. Returns False if they're still down after ``timeout``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(is_key_down(vk) for vk in _MODIFIER_VKS):
            return True
        time.sleep(0.01)
    return False
```

Run `python -m pytest tests/test_win32_input.py -q`. Expected: PASS.

- [ ] **Step 4: Create `shuper_whisper/uia.py`**

```python
"""What precedes the caret in the focused control, via UI Automation.

Best effort: many controls don't expose TextPattern and some apps hang on UIA
calls, so everything runs on one worker thread with a short timeout and
returns None when the answer is unknown.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

_CONTEXT_CHARS = 200
_UIA_TEXT_PATTERN_ID = 10014
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia")
_local = threading.local()


def _client():
    if getattr(_local, "uia", None) is None:
        import comtypes
        import comtypes.client
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as mod
        _local.mod = mod
        _local.uia = comtypes.client.CreateObject(mod.CUIAutomation, interface=mod.IUIAutomation)
    return _local.uia, _local.mod


def _text_before_caret() -> str | None:
    uia, mod = _client()
    element = uia.GetFocusedElement()
    if not element:
        return None
    pattern = element.GetCurrentPattern(_UIA_TEXT_PATTERN_ID)
    if not pattern:
        return None
    text_pattern = pattern.QueryInterface(mod.IUIAutomationTextPattern)
    selection = text_pattern.GetSelection()
    if not selection or selection.Length == 0:
        return None
    caret = selection.GetElement(0).Clone()
    # Collapse to the selection start, then reach back a bounded distance.
    caret.MoveEndpointByRange(mod.TextPatternRangeEndpoint_End, caret,
                              mod.TextPatternRangeEndpoint_Start)
    caret.MoveEndpointByUnit(mod.TextPatternRangeEndpoint_Start, mod.TextUnit_Character,
                             -_CONTEXT_CHARS)
    return caret.GetText(-1)


def _focused_element_id() -> tuple | None:
    uia, _mod = _client()
    element = uia.GetFocusedElement()
    return tuple(element.GetRuntimeId()) if element else None


def _run(fn, timeout: float):
    try:
        return _executor.submit(fn).result(timeout=timeout)
    except FutureTimeout:
        return None
    except Exception:
        return None


def text_before_caret(timeout: float = 0.3) -> str | None:
    """Up to 200 characters before the caret, "" for an empty field, None if unknown."""
    return _run(_text_before_caret, timeout)


def focused_element_id(timeout: float = 0.3) -> tuple | None:
    """UIA RuntimeId of the focused element: identifies "the same field"."""
    return _run(_focused_element_id, timeout)
```

- [ ] **Step 5: Smoke-test UIA by hand**

Open Notepad and type `Hello world.`, then run the command below and click back into Notepad within 3 seconds:

```bash
python -c "import time; time.sleep(3); from shuper_whisper import uia; print(repr(uia.text_before_caret(1.0)))"
```

Expected: `'Hello world.'`. Some apps return `None`, and that's fine; the fallback handles it.

- [ ] **Step 6: Write `tests/test_injector.py`**

```python
"""Tests for TextInjector with fake Win32/UIA providers."""

from shuper_whisper.injector import TextInjector


def make(context=None, hwnd=1):
    sent = []
    state = {"context": context, "hwnd": hwnd}
    inj = TextInjector(
        send=lambda text, backspaces=0: sent.append(text),
        read_context=lambda: state["context"],
        foreground=lambda: state["hwnd"],
        wait_modifiers=lambda: True,
    )
    return inj, sent, state


def test_uses_uia_context():
    inj, sent, _ = make(context="Done.")
    assert inj.inject("next thing.") == " Next thing."
    assert sent == [" Next thing."]


def test_unknown_context_capitalises_without_space():
    inj, sent, _ = make(context=None)
    inj.inject("hello.")
    assert sent == ["Hello."]


def test_falls_back_to_own_history_in_same_window():
    inj, sent, _ = make(context=None)
    inj.inject("first part")
    inj.inject("And more.")
    assert sent == ["First part", " and more."]


def test_history_ignored_in_other_window():
    inj, sent, state = make(context=None)
    inj.inject("first part")
    state["hwnd"] = 2
    inj.inject("then more.")
    assert sent[-1] == "Then more."


def test_empty_text_sends_nothing():
    inj, sent, _ = make()
    assert inj.inject("") == ""
    assert sent == []
```

- [ ] **Step 7: Rewrite `shuper_whisper/injector.py`**

```python
"""Types text at the caret of whatever control has focus.

Uses SendInput unicode keystrokes, so the clipboard is never touched. Context
for spacing/capitalisation comes from UI Automation, falling back to what we
last typed into the same window.
"""

from typing import Callable, Optional

from . import uia
from ._win32_keys import send_text, user32, wait_for_modifiers_released
from .text_rules import join

_HISTORY_CHARS = 200


class TextInjector:
    def __init__(
        self,
        send: Callable[..., None] = send_text,
        read_context: Callable[[], Optional[str]] = uia.text_before_caret,
        foreground: Callable[[], int] = user32.GetForegroundWindow,
        wait_modifiers: Callable[[], bool] = wait_for_modifiers_released,
    ):
        self._send = send
        self._read_context = read_context
        self._foreground = foreground
        self._wait_modifiers = wait_modifiers
        self._last_hwnd: Optional[int] = None
        self._last_typed = ""

    def context(self) -> Optional[str]:
        before = self._read_context()
        if before is not None:
            return before
        if self._last_typed and self._foreground() == self._last_hwnd:
            return self._last_typed
        return None

    def inject(self, text: str) -> str:
        """Type cleaned ``text`` at the caret. Returns exactly what was typed."""
        if not text:
            return ""
        self._wait_modifiers()
        typed = join(text, self.context())
        self._send(typed)
        hwnd = self._foreground()
        if hwnd != self._last_hwnd:
            self._last_hwnd, self._last_typed = hwnd, ""
        self._last_typed = (self._last_typed + typed)[-_HISTORY_CHARS:]
        return typed
```

- [ ] **Step 8: Run the tests**

Run: `python -m pytest tests/test_win32_input.py tests/test_injector.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add shuper_whisper/_win32_keys.py shuper_whisper/uia.py shuper_whisper/injector.py tests/test_win32_input.py tests/test_injector.py
git commit -m "feat(injector): type with SendInput unicode and read caret context via UIA; never touch the clipboard"
```

---

### Task 7: Toggle-only hotkey with visible registration errors

**Files:**
- Modify: `shuper_whisper/hotkey.py`
- Test: `tests/test_hotkey.py` (rewrite)

**Interfaces:**
- Produces: `HotkeyManager(hotkey_str, on_start, on_stop)`, with `.register()` (raises `HotkeyError`), `.unregister()`, `.reset()`, `.active`, `.registered` and `.wait()`.
- Produces: `parse_hotkey(hotkey_str) -> tuple[list[str], str]` (unchanged), and `HotkeyError`.

- [ ] **Step 1: Rewrite `tests/test_hotkey.py`**

Keep the existing `TestParseHotkey` class word for word, and replace everything after it with:

```python
class FakeUser32:
    def __init__(self, ok=True):
        self.ok = ok

    def RegisterHotKey(self, *a):
        return 1 if self.ok else 0

    def UnregisterHotKey(self, *a):
        return 1

    def PeekMessageW(self, *a):
        return 0


class TestToggle:
    def test_first_press_starts_second_stops(self):
        calls = []
        hm = HotkeyManager("f9", lambda: calls.append("start"), lambda: calls.append("stop"))
        hm._on_trigger_press()
        assert hm.active
        hm._on_trigger_press()
        assert calls == ["start", "stop"] and not hm.active

    def test_reset_makes_next_press_start(self):
        calls = []
        hm = HotkeyManager("f9", lambda: calls.append("start"), lambda: calls.append("stop"))
        hm._on_trigger_press()
        hm.reset()
        hm._on_trigger_press()
        assert calls == ["start", "start"]


class TestRegister:
    def test_unknown_key_raises(self):
        hm = HotkeyManager("ctrl+notakey", lambda: None, lambda: None)
        with pytest.raises(HotkeyError, match="notakey"):
            hm.register()

    def test_register_failure_raises(self, monkeypatch):
        monkeypatch.setattr(hotkey_mod, "user32", FakeUser32(ok=False))
        hm = HotkeyManager("f9", lambda: None, lambda: None)
        with pytest.raises(HotkeyError, match="f9"):
            hm.register()
        assert not hm.registered

    def test_register_success(self, monkeypatch):
        monkeypatch.setattr(hotkey_mod, "user32", FakeUser32(ok=True))
        hm = HotkeyManager("f9", lambda: None, lambda: None)
        hm.register()
        assert hm.registered
        hm.unregister()
        assert not hm.registered
```

Change the imports at the top to:

```python
import pytest

from shuper_whisper import hotkey as hotkey_mod
from shuper_whisper.hotkey import HotkeyError, HotkeyManager, parse_hotkey
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_hotkey.py -q`
Expected: FAIL with `ImportError: HotkeyError`.

- [ ] **Step 3: Rewrite the manager in `shuper_whisper/hotkey.py`**

Keep the module docstring, imports, `MODIFIER_NAMES`, `_normalize_modifier` and `parse_hotkey`. Remove `is_key_down` and `is_modifier_down` from the `_win32_keys` import. Replace everything from `# Hotkey ID constants` to the end with:

```python
_HOTKEY_TRIGGER = 1


class HotkeyError(RuntimeError):
    """The hotkey couldn't be registered (bad key name or already taken)."""


class HotkeyManager:
    """Global toggle hotkey: the first press starts dictation, the next stops it.

    RegisterHotKey binds to the registering thread's message queue, so a
    dedicated thread registers the key and pumps WM_HOTKEY messages.
    """

    REGISTER_TIMEOUT = 2.0

    def __init__(self, hotkey_str: str, on_start: Callable[[], None],
                 on_stop: Callable[[], None]):
        self._hotkey_str = hotkey_str
        self._on_start = on_start
        self._on_stop = on_stop
        self._modifiers, self._trigger_key = parse_hotkey(hotkey_str)
        self._mod_flags = get_mod_flags(self._modifiers)
        self._trigger_vk = get_vk(self._trigger_key)
        self._active = False
        self._registered = False
        self._register_ok = False
        self._register_done = threading.Event()
        self._stop_event = threading.Event()
        self._pump_thread: Optional[threading.Thread] = None

    def _message_pump(self) -> None:
        self._register_ok = bool(user32.RegisterHotKey(
            None, _HOTKEY_TRIGGER, self._mod_flags, self._trigger_vk))
        self._register_done.set()
        if not self._register_ok:
            return
        msg = ctypes.wintypes.MSG()
        while not self._stop_event.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_TRIGGER:
                    self._on_trigger_press()
            else:
                time.sleep(0.01)
        user32.UnregisterHotKey(None, _HOTKEY_TRIGGER)

    def _on_trigger_press(self) -> None:
        if self._active:
            self._active = False
            self._on_stop()
        else:
            self._active = True
            self._on_start()

    def reset(self) -> None:
        """Forget an active session (it ended without a second press)."""
        self._active = False

    def register(self) -> None:
        if self._registered:
            return
        if not self._trigger_vk:
            raise HotkeyError(f"Unknown key '{self._trigger_key}' in hotkey '{self._hotkey_str}'")
        self._stop_event.clear()
        self._register_done.clear()
        self._pump_thread = threading.Thread(target=self._message_pump, daemon=True)
        self._pump_thread.start()
        self._register_done.wait(self.REGISTER_TIMEOUT)
        if not self._register_ok:
            self._stop_event.set()
            raise HotkeyError(f"Couldn't register '{self._hotkey_str}'. Another app may be using it.")
        self._registered = True

    def unregister(self) -> None:
        if not self._registered:
            return
        self._stop_event.set()
        if self._pump_thread:
            self._pump_thread.join(timeout=2.0)
            self._pump_thread = None
        self._registered = False
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def registered(self) -> bool:
        return self._registered

    def wait(self) -> None:
        """Block until unregister() or Ctrl+C."""
        while not self._stop_event.is_set():
            self._stop_event.wait(1.0)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_hotkey.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shuper_whisper/hotkey.py tests/test_hotkey.py
git commit -m "refactor(hotkey): toggle-only, raise when registration fails, drop arrow-key format cycling"
```

---

### Task 8: App lifecycle, wiring and removals

**Files:**
- Modify: `shuper_whisper/app.py`, `shuper_whisper/tray.py`, `shuper_whisper/bridge.py`, `shuper_whisper/overlay.py`
- Delete: `shuper_whisper/formatter.py`, `shuper_whisper/theme.py`, `tests/test_formatter.py`, `tests/test_main.py`
- Test: `tests/test_app_lifecycle.py` (new), `tests/test_app_main.py`, `tests/test_overlay.py`

**Interfaces:**
- Consumes: everything from tasks 1–7.
- Produces:
  - `STATE_IDLE`, `STATE_RECORDING`, `STATE_PROCESSING`, `STATE_LOADING` and `STATE_ERROR`.
  - `ShuperWhisperApp.error: str | None`.
  - `ShuperWhisperApp.start()` and `.reload_config(cfg)`, which never raise.
  - `ShuperWhisperApp._on_record_start()` and `._on_record_stop()`.

- [ ] **Step 1: Write `tests/test_app_lifecycle.py`**

```python
"""Lifecycle: failures land in STATE_ERROR and are recoverable."""

import numpy as np
import pytest

from shuper_whisper import app as app_mod
from shuper_whisper.config import AppConfig


class FakeRecorder:
    def __init__(self, device_ref=None, fail=False):
        self.device_ref = device_ref
        self.fail = fail
        self.stream_error = None
        self.audio = np.full(16000, 0.1, np.float32)

    def start_recording(self):
        if self.fail:
            raise RuntimeError("Invalid sample rate")

    def stop_recording(self):
        return self.audio

    def get_levels(self, n):
        return [0.0] * n


class FakeTranscriber:
    def __init__(self, model_size="auto", language="en", fail=False):
        self.fail = fail
        self.loaded = False
        self.language = language
        self.text = "hello world"

    def load_model(self):
        if self.fail:
            raise RuntimeError("model download failed")
        self.loaded = True

    def transcribe(self, audio, initial_prompt=None, hotwords=None):
        return self.text


class FakeHotkeys:
    def __init__(self, hotkey_str, on_start, on_stop):
        self.registered = False
        self.resets = 0

    def register(self):
        self.registered = True

    def unregister(self):
        self.registered = False

    def reset(self):
        self.resets += 1


class FakeOverlay:
    BAR_COUNT = 14
    is_visible = False

    def __getattr__(self, name):
        return lambda *a, **k: None


@pytest.fixture
def make_app(monkeypatch, tmp_path):
    monkeypatch.setattr(app_mod, "AudioRecorder", FakeRecorder)
    monkeypatch.setattr(app_mod, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(app_mod, "HotkeyManager", FakeHotkeys)
    monkeypatch.setattr(app_mod, "RecordingOverlay", lambda **k: FakeOverlay())
    monkeypatch.setattr(app_mod.audio_devices, "migrate", lambda v: v)
    monkeypatch.setattr(app_mod, "save_config", lambda c: None)

    def _make(**cfg):
        a = app_mod.ShuperWhisperApp(AppConfig(**cfg))
        a.dictionary = app_mod.WordDictionary(path=str(tmp_path / "d.json"))
        a.injector = type("I", (), {"typed": [], "inject": lambda self, t: self.typed.append(t) or t})()
        states = []
        a.set_state_callback(states.append)
        a.states = states
        a._run_async = lambda fn, *args: fn(*args)  # run session finish inline
        return a
    return _make


def test_start_reaches_idle(make_app):
    a = make_app()
    a.start()
    assert a.states == ["loading", "idle"] and a.is_running


def test_model_failure_is_error_not_loading(make_app):
    a = make_app()
    a.transcriber.fail = True
    a.start()
    assert a.states[-1] == "error" and "model download failed" in a.error


def test_mic_failure_at_dictation_is_error_and_resets_hotkey(make_app):
    a = make_app()
    a.start()
    a.recorder.fail = True
    a._on_record_start()
    assert a.states[-1] == "error" and "Invalid sample rate" in a.error
    assert a.hotkey_manager.resets == 1


def test_recovers_by_picking_a_working_device(make_app):
    a = make_app()
    a.start()
    a.recorder.fail = True
    a._on_record_start()
    a.reload_config(AppConfig(input_device={"name": "Good Mic", "hostapi": None}))
    assert a.states[-1] == "idle" and a.error is None
    assert a.recorder.device_ref == {"name": "Good Mic", "hostapi": None}


def test_device_change_does_not_reload_model(make_app):
    a = make_app()
    a.start()
    t = a.transcriber
    a.reload_config(AppConfig(input_device={"name": "Good Mic", "hostapi": None}))
    assert a.transcriber is t


def test_full_session_types_clean_text(make_app):
    a = make_app()
    a.start()
    a.transcriber.text = "Hello  there — friend..."
    a._on_record_start()
    a._on_record_stop()
    assert a.injector.typed == ["Hello there, friend"]
    assert a.states[-1] == "idle"


def test_silence_types_nothing(make_app):
    a = make_app()
    a.start()
    a.recorder.audio = np.zeros(16000, np.float32)
    a._on_record_start()
    a._on_record_stop()
    assert a.injector.typed == [] and a.states[-1] == "idle"


def test_second_start_while_finishing_is_ignored(make_app):
    a = make_app()
    a.start()
    a._session_lock.acquire()
    a._on_record_start()
    assert a.hotkey_manager.resets == 1
    assert "recording" not in a.states


def test_legacy_device_index_migrated_on_start(make_app, monkeypatch):
    saved = []
    monkeypatch.setattr(app_mod.audio_devices, "migrate",
                        lambda v: {"name": "B1", "hostapi": "Windows WASAPI"} if v == 75 else v)
    monkeypatch.setattr(app_mod, "save_config", saved.append)
    a = make_app(input_device=75)
    a.start()
    assert a.config.input_device == {"name": "B1", "hostapi": "Windows WASAPI"}
    assert a.recorder.device_ref == a.config.input_device
    assert saved
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_app_lifecycle.py -q`
Expected: FAIL (import errors: `formatter`, `STATE_ERROR` and others).

- [ ] **Step 3: Rewrite the `ShuperWhisperApp` part of `shuper_whisper/app.py`**

Replace everything from the top of the file down to (but not including) `def list_devices()` with:

```python
"""Main application orchestrator and process entry point for ShuperWhisper."""

import ctypes
import multiprocessing
import sys
import threading
from typing import Callable, Optional

import numpy as np

from . import audio_devices
from ._win32_keys import InjectionBlocked
from .audio import AudioRecorder
from .config import AppConfig, load_config, save_config
from .dictionary import WordDictionary
from .hotkey import HotkeyManager
from .injector import TextInjector
from .overlay import RecordingOverlay
from .text_rules import clean
from .transcriber import Transcriber

STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"
STATE_LOADING = "loading"
STATE_ERROR = "error"

# Below this RMS the recording is treated as silence (Whisper hallucinates on it).
SILENCE_RMS_THRESHOLD = 0.005


class ShuperWhisperApp:
    """Wires together audio, transcription, the hotkey, the overlay and typing."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.error: Optional[str] = None
        self._state_callback: Optional[Callable[[str], None]] = None
        self._running = False
        self._session_lock = threading.Lock()
        self._level_timer: Optional[threading.Timer] = None

        self.recorder = AudioRecorder(device_ref=config.input_device)
        self.transcriber = Transcriber(model_size=config.model_size, language=config.language)
        self.injector = TextInjector()
        self.hotkey_manager = self._make_hotkeys(config.hotkey)
        self.dictionary = WordDictionary()
        self.overlay = RecordingOverlay(position=config.overlay_position)

    # -- state ---------------------------------------------------------------

    def set_state_callback(self, callback: Callable[[str], None]) -> None:
        self._state_callback = callback

    def _set_state(self, state: str, error: Optional[str] = None) -> None:
        self.error = error
        if self._state_callback:
            self._state_callback(state)

    def _fail(self, message: str) -> None:
        print(f"[app] ERROR: {message}", flush=True)
        self._set_state(STATE_ERROR, message)

    def _make_hotkeys(self, hotkey: str) -> HotkeyManager:
        return HotkeyManager(hotkey, on_start=self._on_record_start, on_stop=self._on_record_stop)

    def _run_async(self, fn, *args) -> None:
        threading.Thread(target=fn, args=args, daemon=True).start()

    # -- dictation session -----------------------------------------------------

    def _on_record_start(self) -> None:
        if not self._session_lock.acquire(blocking=False):
            self.hotkey_manager.reset()  # previous dictation is still being typed
            return
        try:
            self.recorder.start_recording()
        except Exception as e:
            self._session_lock.release()
            self.hotkey_manager.reset()
            self._fail(f"Microphone: {e}")
            return
        self._set_state(STATE_RECORDING)
        self.overlay.show()
        self._start_level_monitoring()

    def _on_record_stop(self) -> None:
        self._stop_level_monitoring()
        try:
            audio = self.recorder.stop_recording()
        except Exception as e:
            audio = None
            self.recorder.stream_error = str(e)
        self._set_state(STATE_PROCESSING)
        self.overlay.show_processing()
        self._run_async(self._finish_session, audio)

    def _finish_session(self, audio: Optional[np.ndarray]) -> None:
        try:
            if self.recorder.stream_error:
                raise RuntimeError(self.recorder.stream_error)
            if audio is None or float(np.sqrt(np.mean(audio ** 2))) < SILENCE_RMS_THRESHOLD:
                self._set_state(STATE_IDLE)
                return
            text = self.transcriber.transcribe(
                audio,
                initial_prompt=self.dictionary.get_initial_prompt() or None,
                hotwords=self.dictionary.get_hotwords() or None,
            )
            text = clean(text, self.dictionary.get_replacements())
            if text:
                self.injector.inject(text)
            self._set_state(STATE_IDLE)
        except InjectionBlocked as e:
            self._fail(str(e))
        except Exception as e:
            self._fail(f"Dictation failed: {e}")
        finally:
            self.overlay.hide()
            self._session_lock.release()

    def _start_level_monitoring(self) -> None:
        def _update():
            if self.overlay.is_visible:
                self.overlay.update_levels(self.recorder.get_levels(self.overlay.BAR_COUNT))
                self._level_timer = threading.Timer(0.033, _update)
                self._level_timer.daemon = True
                self._level_timer.start()
        _update()

    def _stop_level_monitoring(self) -> None:
        if self._level_timer:
            self._level_timer.cancel()
            self._level_timer = None

    # -- lifecycle -------------------------------------------------------------

    def _migrate_device(self) -> None:
        migrated = audio_devices.migrate(self.config.input_device)
        if migrated != self.config.input_device:
            self.config.input_device = migrated
            self.recorder = AudioRecorder(device_ref=migrated)
            save_config(self.config)

    def start(self) -> None:
        """Load the model and register the hotkey. Never raises; failures
        leave the app in STATE_ERROR with ``self.error`` set."""
        if self._running:
            return
        self._set_state(STATE_LOADING)
        try:
            self._migrate_device()
            if not self.transcriber.loaded:
                self.transcriber.load_model()
            self.hotkey_manager.register()
        except Exception as e:
            self._fail(str(e))
            return
        self._running = True
        self._set_state(STATE_IDLE)
        print(f"[app] Ready. Press {self.config.hotkey} to dictate.", flush=True)

    def shutdown(self, destroy_overlay: bool = True) -> None:
        self._stop_level_monitoring()
        self.hotkey_manager.unregister()
        if destroy_overlay:
            self.overlay.destroy()
        else:
            self.overlay.hide()
        self._running = False

    def reload_config(self, new_config: AppConfig) -> None:
        """Apply settings, touching only what changed. Never raises."""
        old, self.config = self.config, new_config
        self.dictionary.load()
        self.overlay.set_position(new_config.overlay_position)
        try:
            if new_config.input_device != old.input_device:
                self.recorder = AudioRecorder(device_ref=new_config.input_device)
            if new_config.model_size != old.model_size or not self.transcriber.loaded:
                self._set_state(STATE_LOADING)
                self.transcriber = Transcriber(model_size=new_config.model_size,
                                               language=new_config.language)
                self.transcriber.load_model()
            self.transcriber.language = new_config.language
            if new_config.hotkey != old.hotkey or not self.hotkey_manager.registered:
                self.hotkey_manager.unregister()
                self.hotkey_manager = self._make_hotkeys(new_config.hotkey)
                self.hotkey_manager.register()
        except Exception as e:
            self._fail(str(e))
            return
        self._running = True
        self._set_state(STATE_IDLE)

    @property
    def is_running(self) -> bool:
        return self._running

    def run(self) -> None:
        """Console mode: start, then block until Ctrl+C."""
        self.start()
        if not self._running:
            return
        try:
            self.hotkey_manager.wait()
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            self.shutdown()
```

Then, in the rest of `app.py`:

- Replace `list_devices()` with:

```python
def list_devices() -> None:
    """Print available audio input devices and exit."""
    print("Available audio input devices:\n")
    for d in audio_devices.list_input_devices():
        default = " (DEFAULT)" if d.is_default else ""
        print(f"  {d.name}  [{d.to_dict()['hostapi_label']}, {int(d.samplerate)} Hz]{default}")
```

- Delete `_load_env` entirely.
- In `main()`, delete the `# Load API keys ...` comment and the `_load_env()` call.
- Update `main()`'s docstring to: `"""Entry point for the installed ``shuper-whisper`` gui-script; main.py delegates here (issue #11)."""`

- [ ] **Step 4: Update `tests/test_app_main.py` for the removed `_load_env`**

In the `stub_main` fixture, delete the `_load_env` patch line. Then:

- Rename `test_main_enables_dpi_and_loads_env_before_config` to `test_main_enables_dpi_before_config`.
- Replace its docstring with `"""DPI awareness must run before any config/UI work."""`
- Change its assertion to `assert stub_main[:2] == ["dpi", "config"]`.

Delete `tests/test_main.py`; it only tests `_load_env`.

- [ ] **Step 5: Strip format modes and colours from `shuper_whisper/overlay.py`**

- Delete the line `from .config import FORMAT_MODE_LABELS, FORMAT_MODE_ORDER`.
- In `RecordingOverlay`:
  - Change `__init__` to `def __init__(self, position: str = "top_center"):`.
  - Set `self._accent_color = "#ff4466"` and `self._bg_color = "#1a1a2e"` as fixed values.
  - Delete `self._format_mode` and `self._on_format_change`.
- Delete `cycle_format_mode`, `set_on_format_change` and the `format_mode` property.
- Replace `show` with:

```python
    def show(self) -> None:
        """Show the overlay without stealing focus. Thread-safe."""
        self._mode = "hold"
        self._state = "recording"
        self._visible = True
        self._eval("showOverlay('hold', '')")
        if self._hwnd:
            SW_SHOWNOACTIVATE = 8
            ctypes.windll.user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)
            self._position_window()
```

- Replace `set_colors` with:

```python
    def apply_colors(self) -> None:
        self._eval(f"setColors('{self._accent_color}', '{self._bg_color}')")
```

- In the embedded `OVERLAY_HTML`, delete:
  - the `.format-row` CSS rules;
  - the `<div class="format-row" ...>...</div>` element;
  - the `formatRow` variable;
  - the `if (mode === 'toggle') {...}` block inside `showOverlay` (its else branch stays in effect);
  - the `setFormatMode` function.

In `tests/test_overlay.py`:
- Delete `from shuper_whisper.config import FORMAT_MODE_ORDER`.
- Delete `test_default_format_mode` and the whole `TestFormatModeCycling` class.
- Change any `RecordingOverlay(position=..., accent_color=..., bg_color=...)` construction to `RecordingOverlay(position=...)`.

- [ ] **Step 6: Update `shuper_whisper/tray.py`**

- Import `STATE_ERROR` alongside the other states, and add `STATE_ERROR: "#E81123",` to `_COLORS`.
- Replace `_on_state_change` with:

```python
    def _on_state_change(self, state: str) -> None:
        self._current_state = state
        if self._icon is not None:
            self._icon.icon = _make_icon(_COLORS.get(state, _COLORS[STATE_IDLE]))
            detail = self.app.error if state == STATE_ERROR and self.app.error else state.capitalize()
            # Windows caps tray tooltips at 127 characters.
            self._icon.title = f"ShuperWhisper - {detail}"[:127]
```

- In `_setup`, replace the body of `_start_app` with `self.app.start()`, since `start()` no longer raises.
- In `_on_overlay_loaded`, replace the `set_colors(...)` call with `self.app.overlay.apply_colors()`.

- [ ] **Step 7: Update `shuper_whisper/bridge.py`**

Replace `get_devices`, `save_config` and `get_config_options` with:

```python
    def get_devices(self):
        """List input devices (re-scanned, so newly plugged devices show up)."""
        try:
            from . import audio_devices
            audio_devices.refresh()
            return [d.to_dict() for d in audio_devices.list_input_devices()]
        except Exception as e:
            print(f"Error getting devices: {e}")
            return []

    def save_config(self, data):
        """Validate, check the mic, save and apply. Returns {success, config|error}."""
        from . import audio_devices
        from .config import AppConfig, load_config, save_config

        try:
            config = AppConfig(
                hotkey=data.get('hotkey', 'ctrl+shift+space'),
                model_size=data.get('model_size', 'auto'),
                input_device=data.get('input_device'),
                language=data.get('language', 'en'),
                overlay_position=data.get('overlay_position', 'top_center'),
            )
            config.validate()
            if config.input_device != load_config().input_device:
                problem = audio_devices.check(config.input_device)
                if problem:
                    return {'success': False, 'error': f"Can't use that microphone: {problem}"}
            save_config(config)
            if self._app:
                self._app.reload_config(config)
                if self._app.error:
                    return {'success': False, 'error': self._app.error}
            return {'success': True, 'config': config.to_dict()}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_config_options(self):
        """Return available options for config dropdowns."""
        from .config import AppConfig, SUPPORTED_LANGUAGES, VALID_OVERLAY_POSITIONS
        return {
            'models': list(AppConfig.VALID_MODELS),
            'languages': SUPPORTED_LANGUAGES,
            'overlay_positions': list(VALID_OVERLAY_POSITIONS),
        }
```

- [ ] **Step 8: Delete dead modules**

```bash
git rm shuper_whisper/formatter.py shuper_whisper/theme.py tests/test_formatter.py tests/test_main.py
```

Then confirm nothing still references the removed names:

```bash
rg -n "formatter|smart_text|theme|pyperclip|anthropic|format_mode|email_tone|prompt_detail|hotkey_mode|bullet_mode|email_mode|accent_color|bg_color|_load_env|open_stream|close_stream" shuper_whisper tests main.py
```

Expected: no matches, apart from `overlay.py`'s own `_accent_color` / `_bg_color` attributes.

- [ ] **Step 9: Run the whole suite**

Run: `python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add -A shuper_whisper tests
git commit -m "fix(app): failures land in an error state instead of hanging on Loading; remove format modes and the Claude formatter"
```

---

### Task 9: Settings UI catches up

**Files:**
- Modify: `shuper_whisper/ui/src/lib/types.ts`, `ui/src/lib/bridge.ts`, `ui/src/hooks/useConfig.ts`, `ui/src/App.tsx`, `ui/src/components/GeneralTab.tsx`, `ui/src/components/TabNav.tsx`
- Delete: `shuper_whisper/ui/src/components/FormattingTab.tsx`

- [ ] **Step 1: `types.ts`**

Replace `AppConfig`, `ConfigOptions` and `Device` with:

```ts
export interface DeviceRef {
  name: string;
  hostapi: string | null;
}

export interface AppConfig {
  hotkey: string;
  model_size: string;
  input_device: DeviceRef | null;
  language: string;
  overlay_position: string;
}

export interface ConfigOptions {
  models: string[];
  languages: Record<string, string>;
  overlay_positions: string[];
}

export interface Device {
  index: number;
  name: string;
  hostapi: string;
  hostapi_label: string;
  channels: number;
  samplerate: number;
  is_default: boolean;
}
```

- [ ] **Step 2: `bridge.ts`**

Change the `saveConfig` return type to `Promise<{ success: boolean; config?: AppConfig; error?: string }>`. Change the `save_config` member of `PyWebViewAPI` the same way.

- [ ] **Step 3: `useConfig.ts`**

Add `const [saveError, setSaveError] = useState<string | null>(null);`. Replace the `save` callback with:

```ts
  const save = useCallback(async (): Promise<boolean> => {
    if (!config) return false;
    setIsSaving(true);
    setSaveError(null);
    try {
      const result = await saveConfig(config);
      if (!result.success) {
        setSaveError(result.error ?? "Couldn't save settings");
        return false;
      }
      originalConfig.current = { ...config };
      return true;
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Couldn't save settings");
      return false;
    } finally {
      setIsSaving(false);
    }
  }, [config]);
```

Add `saveError` to the returned object.

- [ ] **Step 4: `TabNav.tsx`**

- Change `type Tab` to `"general" | "dictionary"`.
- Delete the `formatting` entry from `tabs` and remove `Type` from the lucide import.

- [ ] **Step 5: `App.tsx`**

- Delete the `FormattingTab` import, the colour `useEffect` block, and the `{activeTab === "formatting" && ...}` block.
- Change `type Tab` to `"general" | "dictionary"`.
- Destructure `saveError` from `useConfig()`.
- Render it just above `<ActionBar ...>`:

```tsx
      {saveError && (
        <div className="mx-8 mb-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-[12px] text-red-300">
          {saveError}
        </div>
      )}
```

`handleSave` already closes the window only on success, so it needs no change.

- [ ] **Step 6: `GeneralTab.tsx`**

- Remove `Palette` from the lucide import, and delete the whole `{/* Appearance */}` block.
- Replace the hotkey hint text with `Press once to start dictating, again to stop.`
- Replace `modelOptions` with:

```tsx
  const modelLabels: Record<string, string> = {
    auto: "Auto (best for this PC)",
    "large-v3-turbo": "Large v3 Turbo",
    "large-v3": "Large v3",
  };
  const modelOptions = options.models.map((m) => ({
    value: m,
    label: modelLabels[m] ?? m.charAt(0).toUpperCase() + m.slice(1),
  }));
```

- Replace `deviceOptions` and the device `StyledSelect` with:

```tsx
  const deviceId = (name: string, hostapi: string | null) => `${name}|${hostapi ?? ""}`;
  const deviceOptions = [
    { value: "__default__", label: "System Default" },
    ...devices.map((d) => ({
      value: deviceId(d.name, d.hostapi),
      label: `${d.name} · ${d.hostapi_label}`,
    })),
  ];
  const currentDevice = config.input_device
    ? deviceId(config.input_device.name, config.input_device.hostapi)
    : "__default__";
```

```tsx
        <StyledSelect
          value={currentDevice}
          onChange={(v) => {
            if (v === "__default__") return updateField("input_device", null);
            const d = devices.find((x) => deviceId(x.name, x.hostapi) === v);
            if (d) updateField("input_device", { name: d.name, hostapi: d.hostapi });
          }}
          options={deviceOptions}
        />
```

- [ ] **Step 7: Delete FormattingTab and build**

```bash
git rm shuper_whisper/ui/src/components/FormattingTab.tsx
cd shuper_whisper/ui && npm install && npm run build
```

Expected: `tsc` and `vite build` finish with no errors.

- [ ] **Step 8: Commit**

```bash
git add -A shuper_whisper/ui
git commit -m "feat(ui): device list by name and host API, surface save errors, drop formatting and colour settings"
```

---

### Task 10: Docs, end-to-end check, PR

**Files:**
- Modify: `README.md`, `CLAUDE.md` (local only; it's gitignored)

- [ ] **Step 1: README**

- Remove every mention of the format modes, email/AI-prompt, Claude/Anthropic, the API key and `.env`, and hold-to-talk.
- Add a short "How it works" paragraph:
  - press the hotkey to start, press it again to stop;
  - text is typed where your cursor is;
  - spoken "new line", "new paragraph", "period", "comma", "question mark" are understood;
  - no internet needed after the model downloads;
  - an NVIDIA GPU is used automatically when present (`pip install -e .[gpu]`).

- [ ] **Step 2: Project CLAUDE.md**

- Remove "anthropic SDK (optional intelligent reformatting)" from Stack, and the Claude bullet under Integrations.
- Change `pip install -e .[dev]` to `pip install -e .[dev,gpu]`.
- Add under Scope Notes: `Design: docs/superpowers/specs/2026-10-04-live-dictation-design.md (stage plans in docs/superpowers/plans/).`

- [ ] **Step 3: Full suite**

Run: `python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 4: Manual end-to-end**

```bash
python main.py
```

Check:
1. Tray turns grey ("Idle"). The console says `Loading Whisper large-v3-turbo on cuda (float16)`.
2. Settings → Input Device → `Voicemeeter Out B1 (...) · WASAPI` → Save. The window closes, the tray stays idle, and there's no "Loading" hang.
3. In Notepad, press the hotkey, say "hello there comma this is a test period new line second line", then press the hotkey again. Expected text: `Hello there, this is a test.` then a newline, then `Second line`. There are no double spaces, and the clipboard keeps whatever was on it before.
4. Select a device that is unplugged → Save: the window shows "Can't use that microphone: ..." inline and stays open.
5. Restart Voicemeeter, then dictate again. It still uses B1, because the device is resolved by name.

- [ ] **Step 5: Commit docs, push, open PR**

```bash
git add README.md
git commit -m "docs: describe toggle dictation, spoken commands and GPU support"
git push -u origin feat/stage1-foundation
source D:/dev/scripts/profile.sh && infisical-load-env && curl -sf -X POST \
  -H "Authorization: token $GITEA_TOKEN" -H "Content-Type: application/json" \
  "$GITEA_URL/api/v1/repos/shuper/shuperwhisper/pulls" \
  -d @- <<'EOF'
{"base":"main","head":"feat/stage1-foundation","title":"Stage 1: fix Voicemeeter B1, clean text, type at caret, drop format modes",
 "body":"Implements stage 1 of docs/superpowers/specs/2026-10-04-live-dictation-design.md.\n\n- Devices stored by name + host API; native-rate capture resampled to 16 kHz (fixes Voicemeeter Out B1 stuck on Loading)\n- Failures land in an error state with a message; picking a working device recovers\n- Deterministic text rules: single spaces, no em-dashes, fillers, spoken commands, dictionary replacements\n- SendInput unicode typing with UIA caret context; clipboard untouched\n- Whisper on CUDA when available (large-v3-turbo), CPU fallback\n- Removed format modes, Claude formatter, hold mode, colour settings\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"}
EOF
```

Expected: JSON with the PR `number` and `html_url`. Never merge it.

- [ ] **Step 6: Whole-branch review**

Review the whole branch once, on the most capable model, against the spec's Stage 1 section and this plan: `git diff main...feat/stage1-foundation`. Fix what it finds in a follow-up commit on the same branch.
