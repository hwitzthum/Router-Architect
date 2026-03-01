"""Integration tests for embedding-based classification — no live Ollama required."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import router.embeddings as _emb
from router.classifier import classify_request
from router.config import EmbeddingConfig, PluginConfig, load_plugins
from router.models import TaskType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_enabled_cfg(**kwargs) -> EmbeddingConfig:
    defaults = dict(
        enabled=True,
        base_url="http://localhost:11434/v1",
        model="nomic-embed-text",
        similarity_threshold=0.75,
        top_k=3,
    )
    defaults.update(kwargs)
    return EmbeddingConfig(**defaults)


def _unit_vec(dim: int, index: int) -> list[float]:
    v = [0.0] * dim
    v[index] = 1.0
    return v


# ---------------------------------------------------------------------------
# TestClassifyRequestWithEmbedding
# ---------------------------------------------------------------------------

class TestClassifyRequestWithEmbedding:
    def setup_method(self):
        _emb._corpus = None

    def test_disabled_by_default_no_change(self):
        """When embedding is disabled (default), classify_request returns keyword result unchanged."""
        messages = [{"role": "user", "content": "write a haiku"}]
        result_no_emb = classify_request(messages)
        result_with_disabled = classify_request(messages, embedding_config=EmbeddingConfig())
        assert result_no_emb.task_type == result_with_disabled.task_type

    def test_overrides_general_result(self):
        """Embedding overrides 'general' when corpus votes unanimously for another type."""
        cfg = _make_enabled_cfg()
        # Pre-load corpus: all items are 'reasoning', vector = [1, 0]
        _emb._corpus = [
            ([1.0, 0.0], TaskType.reasoning),
            ([1.0, 0.0], TaskType.reasoning),
            ([1.0, 0.0], TaskType.reasoning),
        ]
        # Text has no keywords → keyword pass gives 'general'
        messages = [{"role": "user", "content": "xyz xyz xyz"}]
        with patch("router.embeddings.EmbeddingClient") as MockClient:
            instance = MockClient.return_value
            instance.embed_text.return_value = [1.0, 0.0]  # Same direction as corpus
            result = classify_request(messages, embedding_config=cfg)

        assert result.task_type == TaskType.reasoning

    def test_does_not_override_when_vote_split(self):
        """When embedding vote is split, keyword result is retained."""
        cfg = _make_enabled_cfg()
        # Corpus: two different task types near query
        _emb._corpus = [
            ([1.0, 0.0], TaskType.reasoning),
            ([1.0, 0.0], TaskType.code),
            ([1.0, 0.0], TaskType.code),
        ]
        # Text has strong code signal
        messages = [{"role": "user", "content": "debug this python function"}]
        with patch("router.embeddings.EmbeddingClient") as MockClient:
            instance = MockClient.return_value
            instance.embed_text.return_value = [1.0, 0.0]
            result = classify_request(messages, embedding_config=cfg)

        # Split vote → embedding returns None → keyword result (code) kept
        assert result.task_type == TaskType.code

    def test_network_failure_falls_back_to_keyword(self):
        """When embed_text raises, keyword result is preserved."""
        cfg = _make_enabled_cfg()
        _emb._corpus = [([1.0, 0.0], TaskType.reasoning)]
        messages = [{"role": "user", "content": "debug this python function"}]
        with patch("router.embeddings.EmbeddingClient") as MockClient:
            instance = MockClient.return_value
            instance.embed_text.side_effect = Exception("connection refused")
            result = classify_request(messages, embedding_config=cfg)

        assert result.task_type == TaskType.code

    def test_corpus_not_initialized_falls_back_to_keyword(self):
        """When corpus is None, embedding path is skipped immediately."""
        cfg = _make_enabled_cfg()
        _emb._corpus = None
        messages = [{"role": "user", "content": "debug this python function"}]
        with patch("router.embeddings.EmbeddingClient") as MockClient:
            result = classify_request(messages, embedding_config=cfg)
            # EmbeddingClient should not even be constructed
            MockClient.assert_not_called()

        assert result.task_type == TaskType.code

    def test_full_pipeline_embedding_enabled(self):
        """classify_request with enabled config and loaded corpus uses embedding result."""
        cfg = _make_enabled_cfg(top_k=1, similarity_threshold=0.75)
        _emb._corpus = [([1.0, 0.0], TaskType.knowledge_work)]
        # "hello" → no keyword match → general
        messages = [{"role": "user", "content": "hello hello hello"}]
        with patch("router.embeddings.EmbeddingClient") as MockClient:
            instance = MockClient.return_value
            instance.embed_text.return_value = [1.0, 0.0]
            result = classify_request(messages, embedding_config=cfg)

        assert result.task_type == TaskType.knowledge_work


# ---------------------------------------------------------------------------
# TestEmbeddingConfigLoading
# ---------------------------------------------------------------------------

class TestEmbeddingConfigLoading:
    def test_parsed_from_yaml(self, tmp_path: Path):
        """EmbeddingConfig is correctly parsed from plugins.yaml."""
        (tmp_path / "plugins.yaml").write_text(
            "cache:\n  enabled: false\n"
            "safety:\n  jailbreak_detection:\n    enabled: false\n"
            "  pii_redaction:\n    enabled: false\n"
            "  prompt_injection:\n    enabled: false\n"
            "hallucination:\n  enabled: false\n"
            "embedding:\n"
            "  enabled: true\n"
            "  base_url: 'http://my-ollama:11434/v1'\n"
            "  model: 'custom-embed'\n"
            "  similarity_threshold: 0.80\n"
            "  top_k: 5\n"
        )
        plugins = load_plugins(tmp_path)
        assert plugins.embedding.enabled is True
        assert plugins.embedding.base_url == "http://my-ollama:11434/v1"
        assert plugins.embedding.model == "custom-embed"
        assert plugins.embedding.similarity_threshold == 0.80
        assert plugins.embedding.top_k == 5

    def test_defaults_when_section_absent(self, tmp_path: Path):
        """When 'embedding' section is omitted, defaults are applied."""
        (tmp_path / "plugins.yaml").write_text(
            "cache:\n  enabled: false\n"
            "safety:\n  jailbreak_detection:\n    enabled: false\n"
            "  pii_redaction:\n    enabled: false\n"
            "  prompt_injection:\n    enabled: false\n"
            "hallucination:\n  enabled: false\n"
        )
        plugins = load_plugins(tmp_path)
        assert plugins.embedding.enabled is False
        assert plugins.embedding.base_url == "http://localhost:11434/v1"
        assert plugins.embedding.model == "nomic-embed-text"
        assert plugins.embedding.similarity_threshold == 0.75
        assert plugins.embedding.top_k == 3

    def test_disabled_by_default(self, tmp_path: Path):
        """The embedding plugin is disabled by default."""
        (tmp_path / "plugins.yaml").write_text(
            "cache:\n  enabled: false\n"
            "safety:\n  jailbreak_detection:\n    enabled: false\n"
            "  pii_redaction:\n    enabled: false\n"
            "  prompt_injection:\n    enabled: false\n"
            "hallucination:\n  enabled: false\n"
            "embedding:\n  enabled: false\n"
        )
        plugins = load_plugins(tmp_path)
        assert plugins.embedding.enabled is False

    def test_plugin_config_default_factory(self):
        """PluginConfig() creates embedding with disabled=False without arguments."""
        cfg = PluginConfig()
        assert cfg.embedding.enabled is False
        assert cfg.embedding.model == "nomic-embed-text"
