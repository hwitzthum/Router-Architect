"""Configuration loading — YAML files → validated Pydantic models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from router.models import Provider, RoutingRule, TaskType


# ---------------------------------------------------------------------------
# Plugin config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CacheConfig:
    enabled: bool = False
    max_entries: int = 10_000


@dataclass
class SafetyPluginConfig:
    enabled: bool = False


@dataclass
class SafetyConfig:
    jailbreak_detection: SafetyPluginConfig = field(default_factory=SafetyPluginConfig)
    pii_redaction: SafetyPluginConfig = field(default_factory=SafetyPluginConfig)
    prompt_injection: SafetyPluginConfig = field(default_factory=SafetyPluginConfig)


@dataclass
class HallucinationConfig:
    enabled: bool = False
    reroute_on_low_confidence: bool = True
    reroute_target: str = "sonnet"
    confidence_threshold: float = 0.5


@dataclass
class EmbeddingConfig:
    enabled: bool = False
    base_url: str = "http://localhost:11434/v1"
    model: str = "nomic-embed-text"
    similarity_threshold: float = 0.75
    top_k: int = 3


@dataclass
class PluginConfig:
    cache: CacheConfig = field(default_factory=CacheConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    hallucination: HallucinationConfig = field(default_factory=HallucinationConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)


@dataclass
class RouterConfig:
    providers: list[Provider]
    rules: list[RoutingRule]
    default_model: str
    plugins: PluginConfig


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"  Hint: copy config/providers.yaml.example → config/providers.yaml"
        )
    with path.open() as f:
        try:
            return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {path}: {e}") from e


def load_providers(config_dir: Path) -> list[Provider]:
    data = _load_yaml(config_dir / "providers.yaml")
    raw_providers = data.get("providers", [])
    if not raw_providers:
        raise ValueError(
            f"No providers defined in {config_dir / 'providers.yaml'}. "
            "Add at least one provider entry."
        )
    providers = []
    for item in raw_providers:
        try:
            providers.append(Provider(**item))
        except Exception as e:
            raise ValueError(f"Invalid provider config for '{item.get('name', '?')}': {e}") from e
    return providers


def load_routing(config_dir: Path) -> tuple[list[RoutingRule], str]:
    data = _load_yaml(config_dir / "routing.yaml")
    default_model = data.get("default_model", "sonnet")
    rules = []
    for item in data.get("rules", []):
        try:
            item["task_type"] = TaskType(item["task_type"])
            rules.append(RoutingRule(**item))
        except Exception as e:
            raise ValueError(f"Invalid routing rule: {e}") from e
    rules.sort(key=lambda r: r.priority)
    return rules, default_model


def load_plugins(config_dir: Path) -> PluginConfig:
    data = _load_yaml(config_dir / "plugins.yaml")

    cache_data = data.get("cache", {})
    cache = CacheConfig(
        enabled=cache_data.get("enabled", False),
        max_entries=cache_data.get("max_entries", 10_000),
    )

    safety_data = data.get("safety", {})
    safety = SafetyConfig(
        jailbreak_detection=SafetyPluginConfig(
            enabled=safety_data.get("jailbreak_detection", {}).get("enabled", False)
        ),
        pii_redaction=SafetyPluginConfig(
            enabled=safety_data.get("pii_redaction", {}).get("enabled", False)
        ),
        prompt_injection=SafetyPluginConfig(
            enabled=safety_data.get("prompt_injection", {}).get("enabled", False)
        ),
    )

    hall_data = data.get("hallucination", {})
    hallucination = HallucinationConfig(
        enabled=hall_data.get("enabled", False),
        reroute_on_low_confidence=hall_data.get("reroute_on_low_confidence", True),
        reroute_target=hall_data.get("reroute_target", "sonnet"),
        confidence_threshold=hall_data.get("confidence_threshold", 0.5),
    )

    embed_data = data.get("embedding", {})
    embedding = EmbeddingConfig(
        enabled=embed_data.get("enabled", False),
        base_url=embed_data.get("base_url", "http://localhost:11434/v1"),
        model=embed_data.get("model", "nomic-embed-text"),
        similarity_threshold=embed_data.get("similarity_threshold", 0.75),
        top_k=embed_data.get("top_k", 3),
    )

    return PluginConfig(cache=cache, safety=safety, hallucination=hallucination, embedding=embedding)


def load_config(config_dir: Optional[Path] = None) -> RouterConfig:
    """Load the full router configuration from a directory of YAML files."""
    if config_dir is None:
        config_dir = Path(__file__).parent.parent.parent / "config"
    config_dir = Path(config_dir)

    providers = load_providers(config_dir)
    rules, default_model = load_routing(config_dir)
    plugins = load_plugins(config_dir)

    provider_names = {p.name for p in providers}
    if default_model not in provider_names:
        raise ValueError(
            f"default_model '{default_model}' in routing.yaml is not a known provider. "
            f"Available providers: {sorted(provider_names)}"
        )

    for i, rule in enumerate(rules):
        if rule.target_model not in provider_names:
            raise ValueError(
                f"routing.yaml rule[{i}] target_model '{rule.target_model}' is not a known provider. "
                f"Available providers: {sorted(provider_names)}"
            )

        unknown_fallbacks = [m for m in rule.fallback_chain if m not in provider_names]
        if unknown_fallbacks:
            raise ValueError(
                f"routing.yaml rule[{i}] fallback_chain includes unknown provider(s): {unknown_fallbacks}. "
                f"Available providers: {sorted(provider_names)}"
            )

    hall = plugins.hallucination
    if hall.enabled and hall.reroute_on_low_confidence and hall.reroute_target not in provider_names:
        raise ValueError(
            f"plugins.yaml hallucination.reroute_target '{hall.reroute_target}' is not a known provider. "
            f"Available providers: {sorted(provider_names)}"
        )

    return RouterConfig(
        providers=providers,
        rules=rules,
        default_model=default_model,
        plugins=plugins,
    )
