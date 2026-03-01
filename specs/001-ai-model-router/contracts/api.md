# API Contracts: AI Model Router

**Branch**: `001-ai-model-router`
**Date**: 2026-02-28

## Python API (Library Interface)

The router is consumed as a Python library. These are the public function signatures.

### Core Pipeline

```python
def handle_request(messages: list[dict]) -> RequestResult:
    """
    Full routing pipeline: classify → route → call model → track cost.

    Args:
        messages: OpenAI-format chat messages
                  [{"role": "user", "content": "..."}]

    Returns:
        RequestResult with response text, model used, task type,
        estimated cost, latency, and cache hit status.
    """
```

```python
@dataclass
class RequestResult:
    response: str
    model_used: str
    task_type: str          # TaskType enum value
    estimated_cost: float   # USD
    latency_ms: int
    cache_hit: bool
    fallback_triggered: bool
```

### Provider Management

```python
def register_provider(provider: Provider) -> None:
    """Add or update a model provider in the registry."""

def list_providers() -> list[Provider]:
    """Return all configured providers with their current health status."""

def check_provider_health(name: str) -> bool:
    """Check if a provider is reachable (2-second timeout)."""
```

### Classification

```python
def classify_request(messages: list[dict]) -> ClassificationResult:
    """
    Classify a request by task type, complexity, and flags.

    Returns ClassificationResult with task_type, complexity (0.0-1.0),
    token_estimate, requires_tools, factuality_risk.
    """
```

### Routing

```python
def route_request(classification: ClassificationResult) -> RoutingDecision:
    """
    Select the optimal model based on classification signals and cost.

    Returns RoutingDecision with selected_model, fallback_chain, reason.
    """
```

### Model Calling

```python
def call_model(model_name: str, messages: list[dict]) -> str:
    """
    Call a model through the unified OpenAI-compatible interface.

    Raises:
        ProviderUnavailableError: If the provider is not reachable.
        ModelCallError: If the API returns an error.
    """
```

### Cost Reporting

```python
def get_cost_summary(
    since: datetime | None = None,
    until: datetime | None = None,
) -> CostSummary:
    """
    Aggregate cost data over a time range.

    Returns CostSummary with totals by model, by task type,
    and comparison to single-model baseline.
    """

@dataclass
class CostSummary:
    total_cost: float
    cost_by_model: dict[str, float]
    cost_by_task_type: dict[str, float]
    request_count: int
    baseline_cost: float          # What it would cost with Sonnet only
    savings_percentage: float     # (baseline - total) / baseline * 100
```

### Calibration

```python
def run_calibration(
    prompts_file: str = "config/calibration_prompts.yaml",
) -> CalibrationResult:
    """
    Run all calibration prompts against all enabled models.
    Collect responses, compute win rate, latency, cost, regret rate.
    """
```

## CLI Interface

The router also exposes a CLI for operations and debugging.

```
router route "Your prompt here"
    → Routes prompt, prints response + metadata (model, cost, task type)

router providers list
    → Lists all configured providers with health status

router providers check <name>
    → Health check a specific provider

router cost [--since DATE] [--until DATE]
    → Print cost summary

router calibrate [--prompts FILE]
    → Run calibration suite, print metrics report

router classify "Your prompt here"
    → Classify a prompt without routing (debugging)
```

## Configuration File Contracts

### config/providers.yaml

```yaml
providers:
  - name: "sonnet"
    display_name: "Claude Sonnet 4.6"
    category: "cloud"
    base_url: "https://api.anthropic.com/v1"
    api_key_env: "ANTHROPIC_API_KEY"
    model_id: "claude-sonnet-4-6"
    input_price: 3.00
    output_price: 15.00
    max_context_tokens: 200000
    enabled: true

  - name: "gemini"
    display_name: "Gemini 3.1 Pro"
    category: "cloud"
    base_url: "https://generativelanguage.googleapis.com/v1beta"
    api_key_env: "GEMINI_API_KEY"
    model_id: "gemini-3.1-pro"
    input_price: 2.00
    output_price: 12.00
    max_context_tokens: 1000000
    enabled: true

  - name: "qwen"
    display_name: "Qwen 3.5"
    category: "self_hosted"
    base_url: "http://localhost:8000/v1"
    api_key_env: null
    model_id: "Qwen/Qwen3.5"
    input_price: 0.60
    output_price: 3.60
    max_context_tokens: 131072
    enabled: true

  - name: "ollama-qwen35"
    display_name: "Llama 3 (Ollama local)"
    category: "local"
    base_url: "http://localhost:11434/v1"
    api_key_env: null
    model_id: "qwen3.5:cloud"
    input_price: 0.0
    output_price: 0.0
    max_context_tokens: 8192
    enabled: true
```

### config/routing.yaml

```yaml
default_model: "sonnet"

rules:
  - task_type: "reasoning"
    complexity_min: 0.6
    target_model: "gemini"
    fallback_chain: ["sonnet", "ollama-qwen35"]
    priority: 1

  - task_type: "knowledge_work"
    complexity_min: 0.0
    target_model: "sonnet"
    fallback_chain: ["gemini"]
    priority: 2

  - task_type: "code"
    complexity_min: 0.7
    target_model: "gemini"
    fallback_chain: ["sonnet", "qwen"]
    priority: 3

  - task_type: "code"
    complexity_min: 0.0
    complexity_max: 0.7
    target_model: "qwen"
    fallback_chain: ["ollama-qwen35", "sonnet"]
    priority: 4

  - task_type: "extraction"
    complexity_min: 0.0
    target_model: "ollama-qwen35"
    fallback_chain: ["qwen", "sonnet"]
    priority: 5

  - task_type: "general"
    complexity_min: 0.0
    complexity_max: 0.5
    target_model: "qwen"
    fallback_chain: ["ollama-qwen35", "sonnet"]
    priority: 6
```

### config/plugins.yaml

```yaml
cache:
  enabled: false    # P3 feature, disabled by default
  similarity_threshold: 0.92
  max_entries: 10000

safety:
  jailbreak_detection:
    enabled: false  # P3 feature
  pii_redaction:
    enabled: false  # P3 feature
  prompt_injection:
    enabled: false  # P3 feature

hallucination:
  enabled: false    # P3 feature
  reroute_on_low_confidence: true
  reroute_target: "sonnet"
```