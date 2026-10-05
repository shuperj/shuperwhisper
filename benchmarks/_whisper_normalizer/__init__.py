"""Vendored from openai/whisper (MIT), whisper/normalizers at tag v20240930.
Unmodified apart from this file; english.py imports `.basic` relatively,
which works unchanged here."""

from .basic import BasicTextNormalizer
from .english import EnglishTextNormalizer

__all__ = ["BasicTextNormalizer", "EnglishTextNormalizer"]
