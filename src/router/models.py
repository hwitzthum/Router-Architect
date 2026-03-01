"""Pydantic data models and dataclasses for the router system."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Estimate token count from text using a word-to-token heuristic."""
    return max(1, int(len(text.split()) * 1.3))


class ProviderCategory(str, Enum):
    cloud = "cloud"
    self_hosted = "self_hosted"
    local = "local"


class TaskType(str, Enum):
    reasoning = "reasoning"
    knowledge_work = "knowledge_work"
    code = "code"
    extraction = "extraction"
    creative = "creative"
    general = "general"


# ---------------------------------------------------------------------------
# Provider (Pydantic — loaded from config, validated)
# ---------------------------------------------------------------------------

class Provider(BaseModel):
    name: str
    display_name: str
    category: ProviderCategory
    base_url: str
    api_key_env: Optional[str] = None
    model_id: str
    input_price: float
    output_price: float
    cached_input_price: float = 0.0
    max_context_tokens: int
    max_output_tokens: int = 4096
    enabled: bool = True

    @field_validator("input_price", "output_price", "cached_input_price")
    @classmethod
    def prices_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("prices must be >= 0.0")
        return v

    @model_validator(mode="after")
    def local_providers_must_not_require_api_key_env(self) -> "Provider":
        if self.category == ProviderCategory.local:
            if self.api_key_env is not None:
                raise ValueError("local providers must not have api_key_env")
        return self


# ---------------------------------------------------------------------------
# Routing Rule (Pydantic — loaded from config)
# ---------------------------------------------------------------------------

class RoutingRule(BaseModel):
    task_type: TaskType
    complexity_min: float = 0.0
    complexity_max: float = 1.0
    target_model: str
    fallback_chain: list[str] = []
    priority: int = 99

    @field_validator("complexity_min", "complexity_max")
    @classmethod
    def complexity_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("complexity must be between 0.0 and 1.0")
        return v

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Dataclasses (runtime, not persisted to config)
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    task_type: TaskType
    complexity: float           # 0.0 = trivial, 1.0 = frontier-hard
    token_estimate: int
    requires_tools: bool = False
    factuality_risk: bool = False


@dataclass
class RoutingDecision:
    selected_model: str
    fallback_chain: list[str]
    reason: str


@dataclass
class RequestRecord:
    messages: list[dict]
    classification: ClassificationResult
    routing: RoutingDecision
    model_used: str
    response: str
    input_tokens: int
    output_tokens: int
    cost: float
    latency_ms: int
    router_overhead_ms: int
    id: str = dc_field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = dc_field(default_factory=lambda: datetime.now(timezone.utc))
    cache_hit: bool = False
    fallback_triggered: bool = False
    confidence: Optional[float] = None   # hallucination plugin score


@dataclass
class RequestResult:
    response: str
    model_used: str
    task_type: str
    estimated_cost: float
    latency_ms: int
    cache_hit: bool = False
    fallback_triggered: bool = False
    confidence: Optional[float] = None   # hallucination plugin score (0.0–1.0)


@dataclass
class CostSummary:
    total_cost: float
    cost_by_model: dict[str, float]
    cost_by_task_type: dict[str, float]
    request_count: int
    baseline_cost: float        # What same traffic would cost on Sonnet only
    savings_percentage: float
    cache_hit_rate: float = 0.0  # Fraction of requests served from cache


@dataclass
class CalibrationPrompt:
    id: str
    category: str
    prompt: str
    expected_task_type: TaskType
    expected_best_model: Optional[str] = None


@dataclass
class CalibrationResult:
    run_id: str
    timestamp: datetime
    prompts_count: int
    models_tested: list[str]
    win_rate_by_task: dict[str, dict[str, float]]
    avg_latency_by_model: dict[str, float]
    total_cost_by_model: dict[str, float]
    regret_rate: float
    cost_vs_baseline: float
