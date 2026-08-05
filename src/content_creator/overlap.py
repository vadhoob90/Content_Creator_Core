"""Provide overlap capabilities."""

from __future__ import annotations

import re
from typing import Iterable


def phrase_overlap(text: str, corpus: Iterable[str], n: int = 12) -> dict:
    """Return the phrase overlap.

    Args:
        text (str): The text to process.
        corpus (Iterable[str]): The source corpus used for analysis or training.
        n (int): The n value that controls phrase overlap. Defaults to ``12``.

    Returns:
        dict: The resulting dict for phrase overlap.
    """
    words = re.findall(r"\b[\w'-]+\b", text.lower())
    generated = {" ".join(words[index : index + n]) for index in range(max(0, len(words) - n + 1))}
    matches = set()
    for source in corpus:
        source_words = re.findall(r"\b[\w'-]+\b", source.lower())
        source_ngrams = {
            " ".join(source_words[index : index + n])
            for index in range(max(0, len(source_words) - n + 1))
        }
        matches.update(generated & source_ngrams)
    return {"passed": not matches, "matches": sorted(matches)}
