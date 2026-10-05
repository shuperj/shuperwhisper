"""Scoring: word error rate and sentence-break errors.

Words go through Whisper's EnglishTextNormalizer (vendored from openai/whisper,
MIT, as in asr-shootout): casing, punctuation, numbers, contractions, British
spellings and fillers ("um") don't count as errors, so numbers here sit beside
published Whisper WERs. On top, a few spellings that are equally right.
"""

import difflib

from _whisper_normalizer import EnglishTextNormalizer

_normalise = EnglishTextNormalizer()
_SAME = {"alright": "all right", "whatnot": "what not", "okay": "ok", "standup": "stand up",
         "github": "git hub", "cause": "because", "gonna": "going to", "wanna": "want to"}


def words(text: str) -> list[str]:
    out = []
    for w in _normalise(text).split():
        out += _SAME.get(w, w).split()
    return out


def wer(expected: str, got: str) -> tuple[int, int]:
    """(word errors, expected word count): substitutions + deletions + insertions."""
    ref, hyp = words(expected), words(got)
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[len(hyp)], len(ref)


def _tokens(text: str) -> list[tuple[str, bool]]:
    """(lowercased word, ends a sentence) for each word."""
    out = []
    for raw in text.split():
        word = "".join(c for c in raw.lower() if c.isalnum() or c == "'")
        if word:
            out.append((word, raw.rstrip("\"')").endswith((".", "?", "!"))))
    return out


def sentence_breaks(expected: str, got: str) -> tuple[int, int]:
    """(false breaks, missed breaks) over the words both texts share."""
    ref, hyp = _tokens(expected), _tokens(got)
    matcher = difflib.SequenceMatcher(None, [w for w, _ in ref], [w for w, _ in hyp], autojunk=False)
    false = missed = 0
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            want, have = ref[block.a + k][1], hyp[block.b + k][1]
            false += have and not want
            missed += want and not have
    return false, missed
