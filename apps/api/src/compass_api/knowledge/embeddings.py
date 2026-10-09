"""Turning text into vectors.

`EmbeddingProvider` is the seam. The implementation here is the **hashing trick**: tokens
and bigrams are hashed into a fixed number of dimensions with a signed count, then L2
normalised. It is a real technique, not a stub - it gives genuine lexical retrieval with
no model, no network and no account, and it is exactly reproducible, which is what makes
retrieval testable.

What it does not give is semantic matching: "guardar dinheiro" will not match "poupança"
unless the words overlap. A model-based embedder behind this same protocol is the upgrade,
and it is a configuration change rather than a rewrite.

Hashing uses blake2b rather than `hash()`, which is salted per process - vectors must be
identical across restarts or a stored index stops matching new queries.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from itertools import pairwise
from typing import Protocol, runtime_checkable

#: Enough to keep collisions rare for a corpus of this size, small enough to stay cheap.
DEFAULT_DIMENSIONS = 512

_TOKEN = re.compile(r"[a-z0-9]+")

#: Words carrying no retrieval signal in Portuguese or English. A short list on purpose:
#: aggressive stop-word removal hurts more than it helps at this corpus size.
STOP_WORDS = frozenset(
    [
        "a",
        "o",
        "e",
        "de",
        "da",
        "do",
        "das",
        "dos",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "um",
        "uma",
        "uns",
        "umas",
        "para",
        "por",
        "com",
        "que",
        "se",
        "ao",
        "aos",
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "that",
        "is",
        "are",
        "be",
        "as",
        "at",
        "by",
        "from",
        "it",
        "its",
        "this",
        "these",
    ]
)

Vector = tuple[float, ...]


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Produces a vector for each text, all of the same dimension."""

    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[Vector]: ...


def tokenize(text: str) -> list[str]:
    """Lower-case, strip accents, drop stop words."""
    decomposed = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return [token for token in _TOKEN.findall(decomposed.lower()) if token not in STOP_WORDS]


def _bucket(term: str, dimensions: int) -> tuple[int, float]:
    """Stable bucket and sign for a term."""
    digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % dimensions, 1.0 if value & (1 << 63) else -1.0


class HashingEmbeddings:
    """`EmbeddingProvider` using the hashing trick over tokens and bigrams."""

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: Sequence[str]) -> list[Vector]:
        return [self.embed_one(text) for text in texts]

    def embed_one(self, text: str) -> Vector:
        tokens = tokenize(text)
        # Bigrams give a little phrase sensitivity: "reserva emergencia" scores higher
        # than the two words apart.
        terms = Counter(tokens)
        terms.update(f"{first}_{second}" for first, second in pairwise(tokens))

        vector = [0.0] * self._dimensions
        for term, count in terms.items():
            index, sign = _bucket(term, self._dimensions)
            # Sub-linear term frequency: a word repeated ten times is not ten times as
            # important.
            vector[index] += sign * (1.0 + math.log(count))
        return _normalize(vector)


def _normalize(vector: list[float]) -> Vector:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return tuple(vector)
    return tuple(value / norm for value in vector)


def cosine_similarity(left: Vector, right: Vector) -> float:
    """Dot product of two normalised vectors, clamped to 0-1.

    Negative similarity means "shares nothing and then some", which is not a useful
    distinction for ranking, so it is floored at zero.
    """
    return max(0.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True))))
