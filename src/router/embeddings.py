"""Embedding-based semantic classification — optional refinement layer."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from router.models import CalibrationPrompt, TaskType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level corpus state (None until initialize_corpus is called)
# Each entry is (embedding_vector, expected_task_type).
# ---------------------------------------------------------------------------

_corpus: Optional[list[tuple[list[float], TaskType]]] = None
_corpus_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Pure math
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. No external dependencies."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Embedding client (thin wrapper around openai SDK)
# ---------------------------------------------------------------------------

class EmbeddingClient:
    """Wraps an OpenAI-compatible /v1/embeddings endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "nomic-embed-text",
        api_key: str = "local",
    ) -> None:
        from openai import OpenAI
        self._model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def embed_text(self, text: str) -> list[float]:
        """Return the embedding vector for *text*. Raises on any API error."""
        response = self._client.embeddings.create(input=text, model=self._model)
        return response.data[0].embedding


# ---------------------------------------------------------------------------
# Corpus initialization
# ---------------------------------------------------------------------------

def is_corpus_initialized() -> bool:
    """Return True if the embedding corpus has been populated."""
    return _corpus is not None


def initialize_corpus(
    prompts: list[CalibrationPrompt],
    client: EmbeddingClient,
    force: bool = False,
) -> None:
    """
    Pre-compute embeddings for all calibration prompts and store them in the
    module-level corpus. Idempotent — skips if corpus is already populated
    (unless *force* is True). Failed individual embeds are logged and skipped.
    """
    global _corpus
    if _corpus is not None and not force:
        return  # Already initialized

    with _corpus_lock:
        if _corpus is not None and not force:
            return  # Double-checked locking

        corpus: list[tuple[list[float], TaskType]] = []
        for prompt in prompts:
            try:
                embedding = client.embed_text(prompt.prompt)
                corpus.append((embedding, prompt.expected_task_type))
            except Exception as exc:
                logger.warning("Failed to embed calibration prompt %s: %s", prompt.id, exc)

        _corpus = corpus
        logger.info("Embedding corpus initialized with %d prompts", len(_corpus))


# ---------------------------------------------------------------------------
# k-NN classification
# ---------------------------------------------------------------------------

def classify_by_similarity(
    query_embedding: list[float],
    k: int = 3,
    threshold: float = 0.75,
) -> Optional[TaskType]:
    """
    Return a TaskType when the top-k corpus neighbors are UNANIMOUS and ALL
    score at or above *threshold*. Returns None if:
      - corpus is empty or not initialized
      - the best score is below *threshold*
      - the top-k neighbors do not all agree on the same TaskType
    """
    if not _corpus:
        return None

    # Score every item in corpus
    scored: list[tuple[float, TaskType]] = [
        (cosine_similarity(query_embedding, emb), task_type)
        for emb, task_type in _corpus
    ]

    # Sort descending by similarity
    scored.sort(key=lambda x: x[0], reverse=True)

    # Take top-k (may be fewer if corpus is smaller)
    top_k = scored[: min(k, len(scored))]

    # All top-k must be above threshold
    if any(sim < threshold for sim, _ in top_k):
        return None

    # All top-k must agree on task type (unanimity)
    task_types = {tt for _, tt in top_k}
    if len(task_types) != 1:
        return None

    return task_types.pop()
