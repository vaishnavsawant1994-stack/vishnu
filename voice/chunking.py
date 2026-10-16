"""Deterministic long-form text chunking for speech generation."""

from __future__ import annotations

import re


MAX_LONG_FORM_CHARACTERS = 50_000
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+")


def chunk_speech_text(text: str, *, max_characters: int = 1_500) -> tuple[str, ...]:
    """Split long speech text at sentence/word boundaries without losing text.

    The utility is engine independent. It returns textual chunks only; audio
    joining/crossfading remains the responsibility of the selected audio
    pipeline/provider because encoded formats cannot be safely byte-concatenated.
    """

    normalized = text.strip()
    if not normalized:
        raise ValueError("speech text cannot be empty")
    if len(normalized) > MAX_LONG_FORM_CHARACTERS:
        raise ValueError(f"speech text exceeds {MAX_LONG_FORM_CHARACTERS} characters")
    if not 100 <= max_characters <= 5_000:
        raise ValueError("max_characters must be between 100 and 5000")
    if len(normalized) <= max_characters:
        return (normalized,)

    sentences = _SENTENCE_BOUNDARY.split(normalized)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_characters:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_oversize_sentence(sentence, max_characters))
            continue
        candidate = sentence if not current else f"{current} {sentence}"
        if len(candidate) <= max_characters:
            current = candidate
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return tuple(chunks)


def _split_oversize_sentence(sentence: str, limit: int) -> list[str]:
    words = sentence.split()
    if not words:
        return [sentence[index : index + limit] for index in range(0, len(sentence), limit)]

    chunks: list[str] = []
    current = ""
    for word in words:
        if len(word) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(word[index : index + limit] for index in range(0, len(word), limit))
            continue
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= limit:
            current = candidate
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks
