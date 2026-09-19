"""Small, dependency-free BM25 implementation for user-scoped chunk search."""

import math
import re
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Bm25Hit:
    chunk_id: uuid.UUID
    score: float


@dataclass(frozen=True)
class Bm25Document:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    heading_path: str
    content: str


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """Tokenize ASCII words and CJK characters for mixed-language documents."""
    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]


class Bm25Index:
    """Pre-tokenized BM25 corpus that can be reused until documents change."""

    def __init__(self, documents: Sequence[Bm25Document], k1: float = 1.5, b: float = 0.75):
        self.documents = tuple(documents)
        self.k1 = k1
        self.b = b
        self._tokenized = tuple(
            (document, tokenize(document.content)) for document in self.documents
        )
        self._document_count = len(self._tokenized)
        lengths = [len(tokens) for _, tokens in self._tokenized]
        self._average_length = sum(lengths) / max(self._document_count, 1)
        self._document_frequency: Counter[str] = Counter(
            term for _, tokens in self._tokenized for term in set(tokens)
        )

    def search(self, query: str, limit: int = 10) -> list[Bm25Hit]:
        if not self.documents or limit <= 0:
            return []
        query_terms = set(tokenize(query))
        if not query_terms:
            return []

        hits: list[Bm25Hit] = []
        for document, tokens in self._tokenized:
            document_length = len(tokens)
            term_frequency = Counter(tokens)
            score = 0.0
            for term in query_terms:
                frequency = term_frequency.get(term, 0)
                if frequency == 0:
                    continue
                idf = math.log(
                    1 + (self._document_count - self._document_frequency[term] + 0.5)
                    / (self._document_frequency[term] + 0.5)
                )
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * document_length / max(self._average_length, 1)
                )
                score += idf * frequency * (self.k1 + 1) / denominator
            if score > 0:
                hits.append(Bm25Hit(chunk_id=document.chunk_id, score=score))

        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]


def search(
    query: str,
    documents: Sequence[tuple[uuid.UUID, str]],
    limit: int = 10,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[Bm25Hit]:
    """Return the highest-scoring documents using Okapi BM25."""
    index = Bm25Index(
        [
            Bm25Document(
                chunk_id=chunk_id,
                document_id=uuid.UUID(int=0),
                filename="",
                heading_path="",
                content=content,
            )
            for chunk_id, content in documents
        ],
        k1=k1,
        b=b,
    )
    return index.search(query, limit=limit)
