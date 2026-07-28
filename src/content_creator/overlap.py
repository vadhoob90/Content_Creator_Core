from __future__ import annotations

import re
from typing import Iterable


def phrase_overlap(text: str, corpus: Iterable[str], n: int = 12) -> dict:
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
