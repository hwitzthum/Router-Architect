"""Unit tests for configuration loading (T016)."""

from pathlib import Path

import pytest
import yaml

from router.config import load_config, load_providers, load_routing, load_plugins
from router.models import ProviderCategory, TaskType


def write_yaml(path: Path, data: dict):
    with path.open("w") as f:
        yaml.dump(data, f)


@pytest.fixture
def minimal_config_dir(tmp_path):
    """A config directory with minimal valid YAML files."""
    write_yaml(tmp_path / "providers.yaml", {
        "providers": [
            {
                "name": "sonnet",
                "display_name": "Claude",
                "category": "cloud",
                "base_url": "https://api.anthropic.com/v1",
                "api_key_env": "ANTHROPIC_API_KEY",
                "model_id": "claude-sonnet-4-6",
                "input_price": 3.0,
                "output_price": 15.0,
                "max_context_tokens": 200_000,
                "enabled": True,
            },
            {
                "name": "ollama-qwen35",
                "display_name": "Llama 3",
                "category": "local",
                "base_url": "http://localhost:11434/v1",
                "api_key_env": None,
                "model_id": "qwen3.5:cloud",
                "input_price": 0.0,
                "output_price": 0.0,
                "max_context_tokens": 8192,
                "enabled": True,
            },
        ]
    })
    write_yaml(tmp_path / "routing.yaml", {
        "default_model": "sonnet",
        "rules": [
            {
                "task_type": "reasoning",
                "complexity_min": 0.6,
                "complexity_max": 1.0,
                "target_model": "sonnet",
                "fallback_chain": [],
                "priority": 1,
            }
        ],
    })
    write_yaml(tmp_path / "plugins.yaml", {
        "cache": {"enabled": False},
        "safety": {
            "jailbreak_detection": {"enabled": False},
            "pii_redaction": {"enabled": False},
            "prompt_injection": {"enabled": False},
        },
        "hallucination": {"enabled": False},
    })
    return tmp_path


class TestLoadProviders:
    def test_loads_providers(self, minimal_config_dir):
        providers = load_providers(minimal_config_dir)
        assert len(providers) == 2
        names = [p.name for p in providers]
        assert "sonnet" in names
        assert "ollama-qwen35" in names

    def test_local_provider_zero_price(self, minimal_config_dir):
        providers = load_providers(minimal_config_dir)
        local = next(p for p in providers if p.category == ProviderCategory.local)
        assert local.input_price == 0.0
        assert local.output_price == 0.0
        assert local.cached_input_price == 0.0

    def test_repo_config_has_expected_sonnet_and_gemini_pricing(self):
        repo_config_dir = Path(__file__).resolve().parents[2] / "config"
        providers = load_providers(repo_config_dir)
        by_name = {p.name: p for p in providers}

        sonnet = by_name["sonnet"]
        gemini = by_name["gemini"]

        assert sonnet.input_price == 3.0
        assert sonnet.output_price == 15.0
        assert sonnet.cached_input_price == 0.3

        assert gemini.input_price == 2.0
        assert gemini.output_price == 12.0
        assert gemini.cached_input_price == 0.2

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_providers(tmp_path)

    def test_invalid_provider_raises(self, tmp_path):
        write_yaml(tmp_path / "providers.yaml", {
            "providers": [{"name": "bad"}]  # Missing required fields
        })
        with pytest.raises(ValueError, match="Invalid provider config"):
            load_providers(tmp_path)


class TestLoadRouting:
    def test_loads_rules_sorted_by_priority(self, minimal_config_dir):
        rules, default = load_routing(minimal_config_dir)
        assert default == "sonnet"
        assert len(rules) == 1
        assert rules[0].task_type == TaskType.reasoning

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_routing(tmp_path)


class TestLoadPlugins:
    def test_all_disabled_by_default(self, minimal_config_dir):
        plugins = load_plugins(minimal_config_dir)
        assert plugins.cache.enabled is False
        assert plugins.safety.jailbreak_detection.enabled is False
        assert plugins.hallucination.enabled is False


class TestLoadConfig:
    def test_full_config_loads(self, minimal_config_dir):
        config = load_config(minimal_config_dir)
        assert len(config.providers) == 2
        assert config.default_model == "sonnet"
        assert config.plugins.cache.enabled is False

    def test_invalid_rule_target_model_raises(self, minimal_config_dir):
        routing_path = minimal_config_dir / "routing.yaml"
        routing = yaml.safe_load(routing_path.read_text())
        routing["rules"][0]["target_model"] = "missing-model"
        write_yaml(routing_path, routing)

        with pytest.raises(ValueError, match="target_model 'missing-model'"):
            load_config(minimal_config_dir)

    def test_invalid_rule_fallback_model_raises(self, minimal_config_dir):
        routing_path = minimal_config_dir / "routing.yaml"
        routing = yaml.safe_load(routing_path.read_text())
        routing["rules"][0]["fallback_chain"] = ["missing-fallback"]
        write_yaml(routing_path, routing)

        with pytest.raises(ValueError, match="fallback_chain includes unknown provider"):
            load_config(minimal_config_dir)

    def test_invalid_hallucination_reroute_target_raises(self, minimal_config_dir):
        plugins_path = minimal_config_dir / "plugins.yaml"
        plugins = yaml.safe_load(plugins_path.read_text())
        plugins["hallucination"] = {
            "enabled": True,
            "reroute_on_low_confidence": True,
            "reroute_target": "missing-reroute-target",
            "confidence_threshold": 0.5,
        }
        write_yaml(plugins_path, plugins)

        with pytest.raises(ValueError, match="hallucination.reroute_target 'missing-reroute-target'"):
            load_config(minimal_config_dir)
