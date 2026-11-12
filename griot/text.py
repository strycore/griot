"""Cutting text into the pieces an engine synthesizes one at a time.

The gateway streams: it sends each piece's audio as soon as it exists. So the
first piece is kept as small as possible (one sentence) to start speaking
early, and the rest are packed into larger pieces for steadier prosody.
"""
from __future__ import annotations

import re

_SENTENCE = re.compile(r".+?(?:[.!?…]+(?=\s|$)|\n+|$)", re.DOTALL)


def split_sentences(text: str) -> list[str]:
    return [m.group().strip() for m in _SENTENCE.finditer(text) if m.group().strip()]


def chunk(text: str, max_chars: int) -> list[str]:
    """Split `text` into speakable pieces of roughly `max_chars`.

    The first sentence always stands alone. A single sentence longer than
    `max_chars` is left whole -- cutting mid-sentence sounds worse than a late
    chunk.
    """
    sentences = split_sentences(text)
    if not sentences:
        return []
    chunks = [sentences[0]]
    current = ""
    for sentence in sentences[1:]:
        if current and len(current) + 1 + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks
