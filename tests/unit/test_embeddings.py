"""Unit tests for the embeddings module — no network calls."""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

import router.embeddings as _emb
from router.embeddings import (
    EmbeddingClient,
    classify_by_similarity,
    cosine_similarity,
    initialize_corpus,
)
from router.models import CalibrationPrompt, TaskType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prompt(id: str, task_type: TaskType) -> CalibrationPrompt:
    return CalibrationPrompt(
        id=id,
        category=task_type.value,
        prompt=f"prompt text for {id}",
        expected_task_type=task_type,
    )


def _unit_vec(dim: int, index: int) -> list[float]:
    """Return a unit vector with 1.0 at *index* and 0.0 elsewhere."""
    v = [0.0] * dim
    v[index] = 1.0
    return v


# ---------------------------------------------------------------------------
# TestCosineSimilarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = _unit_vec(3, 0)
        b = _unit_vec(3, 1)
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_zero_vector_a(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == pytest.approx(0.0)

    def test_zero_vector_b(self):
        assert cosine_similarity([1.0, 2.0], [0.0, 0.0]) == pytest.approx(0.0)

    def test_commutative(self):
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        assert cosine_similarity(a, b) == pytest.approx(cosine_similarity(b, a))

    def test_partial_similarity(self):
        # 45-degree angle → cos(45°) ≈ 0.707
        a = [1.0, 0.0]
        b = [1.0, 1.0]
        expected = 1.0 / math.sqrt(2)
        assert cosine_similarity(a, b) == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# TestClassifyBySimilarity
# ---------------------------------------------------------------------------

class TestClassifyBySimilarity:
    def setup_method(self):
        # Reset global corpus before each test
        _emb._corpus = None

    def test_none_when_corpus_empty(self):
        _emb._corpus = []
        result = classify_by_similarity([1.0, 0.0], k=3, threshold=0.75)
        assert result is None

    def test_none_when_corpus_not_initialized(self):
        _emb._corpus = None
        result = classify_by_similarity([1.0, 0.0], k=3, threshold=0.75)
        assert result is None

    def test_none_below_threshold(self):
        # All neighbors have low similarity
        _emb._corpus = [(_unit_vec(4, 0), TaskType.reasoning)]
        query = _unit_vec(4, 1)  # orthogonal → similarity 0.0
        result = classify_by_similarity(query, k=1, threshold=0.75)
        assert result is None

    def test_none_when_vote_split(self):
        # Two neighbors of different task types, both above threshold
        v = [1.0, 1.0, 0.0, 0.0]
        _emb._corpus = [(v[:], TaskType.reasoning), (v[:], TaskType.code)]
        result = classify_by_similarity(v, k=2, threshold=0.75)
        assert result is None

    def test_returns_task_type_on_unanimous_top_k(self):
        v = [1.0, 0.0]
        _emb._corpus = [
            (v[:], TaskType.reasoning),
            (v[:], TaskType.reasoning),
            (v[:], TaskType.reasoning),
        ]
        result = classify_by_similarity(v, k=3, threshold=0.75)
        assert result == TaskType.reasoning

    def test_k1_unanimous(self):
        v = [1.0, 0.0]
        _emb._corpus = [(v[:], TaskType.code)]
        result = classify_by_similarity(v, k=1, threshold=0.75)
        assert result == TaskType.code

    def test_k3_with_only_2_corpus_items(self):
        # k=3 but corpus has only 2 items — should use all available
        v = [1.0, 0.0, 0.0]
        _emb._corpus = [(v[:], TaskType.extraction), (v[:], TaskType.extraction)]
        result = classify_by_similarity(v, k=3, threshold=0.75)
        assert result == TaskType.extraction

    def test_third_neighbor_below_threshold_returns_none(self):
        # k=3, first two are unanimous and high, third is below threshold
        v_high = [1.0, 0.0]
        v_low = [0.0, 1.0]  # orthogonal → similarity 0.0 with query [1,0]
        _emb._corpus = [
            (v_high, TaskType.reasoning),
            (v_high, TaskType.reasoning),
            (v_low, TaskType.reasoning),
        ]
        result = classify_by_similarity([1.0, 0.0], k=3, threshold=0.75)
        assert result is None  # v_low fails threshold check


# ---------------------------------------------------------------------------
# TestInitializeCorpus
# ---------------------------------------------------------------------------

class TestInitializeCorpus:
    def setup_method(self):
        _emb._corpus = None

    def test_populates_corpus(self):
        prompts = [_make_prompt("p1", TaskType.reasoning)]
        mock_client = MagicMock(spec=EmbeddingClient)
        mock_client.embed_text.return_value = [0.1, 0.2, 0.3]

        initialize_corpus(prompts, mock_client)

        assert _emb._corpus is not None
        assert len(_emb._corpus) == 1
        stored_vec, stored_task_type = _emb._corpus[0]
        assert stored_vec == [0.1, 0.2, 0.3]
        assert stored_task_type == TaskType.reasoning

    def test_handles_failed_embed_gracefully(self):
        p1 = _make_prompt("p1", TaskType.reasoning)
        p2 = _make_prompt("p2", TaskType.code)
        mock_client = MagicMock(spec=EmbeddingClient)
        # p1 embed raises, p2 succeeds
        mock_client.embed_text.side_effect = [Exception("timeout"), [0.5, 0.5]]

        initialize_corpus([p1, p2], mock_client)

        assert _emb._corpus is not None
        assert len(_emb._corpus) == 1  # Only p2 made it
        _, stored_task_type = _emb._corpus[0]
        assert stored_task_type == TaskType.code

    def test_idempotent(self):
        p = _make_prompt("p1", TaskType.reasoning)
        mock_client = MagicMock(spec=EmbeddingClient)
        mock_client.embed_text.return_value = [1.0, 0.0]

        initialize_corpus([p], mock_client)
        first_corpus = _emb._corpus
        call_count_after_first = mock_client.embed_text.call_count

        # Second call should be a no-op
        initialize_corpus([p], mock_client)
        assert _emb._corpus is first_corpus  # Same object
        assert mock_client.embed_text.call_count == call_count_after_first  # No new calls

    def test_empty_prompts_sets_empty_corpus(self):
        mock_client = MagicMock(spec=EmbeddingClient)
        initialize_corpus([], mock_client)
        assert _emb._corpus == []


# ---------------------------------------------------------------------------
# TestEmbeddingClient
# ---------------------------------------------------------------------------

class TestEmbeddingClient:
    def test_constructs_with_ollama_defaults(self):
        with patch("openai.OpenAI"):
            client = EmbeddingClient()
            assert client._model == "nomic-embed-text"

    def test_constructs_with_custom_params(self):
        with patch("openai.OpenAI"):
            client = EmbeddingClient(
                base_url="http://example.com/v1",
                model="my-embed-model",
                api_key="test-key",
            )
            assert client._model == "my-embed-model"
