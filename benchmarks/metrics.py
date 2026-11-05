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


def word_ops(expected: str, got: str) -> list[tuple[str, str, str]]:
    """Word alignment: ("=", ref, hyp), ("~", ref, hyp) substituted,
    ("-", ref, "") deleted or ("+", "", hyp) inserted, in order."""
    ref, hyp = words(expected), words(got)
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    ops = []
    i, j = n, m
    # Among equally short alignments prefer a match, then an insertion or
    # deletion, then a substitution: "over Monday. I'm going" lines Monday
    # up with Monday rather than with the last invented word.
    while i or j:
        if i and j and ref[i - 1] == hyp[j - 1] and d[i][j] == d[i - 1][j - 1]:
            ops.append(("=", ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif j and d[i][j] == d[i][j - 1] + 1:
            ops.append(("+", "", hyp[j - 1]))
            j -= 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            ops.append(("-", ref[i - 1], ""))
            i -= 1
        else:
            ops.append(("~", ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
    return ops[::-1]


def wer(expected: str, got: str) -> tuple[int, int]:
    """(word errors, expected word count): substitutions + deletions + insertions."""
    ops = word_ops(expected, got)
    return sum(op != "=" for op, _r, _h in ops), sum(op != "+" for op, _r, _h in ops)


def invented(expected: str, got: str, dictionary: str = "") -> list[str]:
    """Words typed that weren't said.

    Each run of errors between matching words is a block. A block whose
    typed letters spell what was said ("voice meter" for "Voicemeeter",
    "pi web view" for "pywebview") is a spelling, not an invention. Otherwise
    its extra words are invented, and so is any dictionary word typed in
    place of a word that wasn't it ("try gitea the whole thing" for
    "moving"). ``dictionary`` is the hotwords string ("a, b, c").
    """
    dict_words = {w for entry in dictionary.split(",") for w in words(entry)}
    out, block = [], []
    for op in word_ops(expected, got) + [("=", "", "")]:
        if op[0] != "=":
            block.append(op)
            continue
        if block:
            refs = [r for _o, r, _h in block if r]
            hyps = [h for _o, _r, h in block if h]
            a, b = "".join(refs), "".join(hyps)
            if not (a and b and difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.75):
                extra = len(hyps) - len(refs)
                # the extra words: those least like anything said
                ranked = sorted(hyps, key=lambda h: max(
                    (difflib.SequenceMatcher(None, h, r).ratio() for r in refs), default=0.0))
                picked = ranked[:max(extra, 0)]
                picked += [h for h in hyps if h in dict_words and h not in refs and h not in picked]
                out += [h for h in hyps if h in picked]
        block = []
    return out


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
