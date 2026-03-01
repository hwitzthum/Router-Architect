# Data Model: AI Model Router

**Branch**: `001-ai-model-router`
**Date**: 2026-02-28

## Entities

### ProviderCategory (Enum)

Classifies the hosting type of a model provider.

| Value | Description |
|-------|-------------|
| `cloud` | Hosted API with per-token billing (Anthropic, Google) |
| `self_hosted` | Self-managed endpoint with amortized cost (vLLM/SGLang) |
| `local` | Locally-run model with zero marginal cost (Ollama) |

### Provider

A configured model endpoint available for routing.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unique identifier (e.g., "sonnet", "gemini", "qwen", "ollama-qwen35") |
| `display_name` | string | yes | Human-readable name (e.g., "Claude Sonnet 4.6") |
| `category` | ProviderCategory | yes | cloud, self_hosted, or local |
| `base_url` | string | yes | API base URL (e.g., "http://localhost:11434/v1") |
| `api_key_env` | string | no | Environment variable name holding the API key (null for local) |
| `model_id` | string | yes | Model identifier sent to the API (e.g., "claude-sonnet-4-6", "qwen3.5:cloud") |
| `input_price` | float | yes | Price per million input tokens (0.0 for local) |
| `output_price` | float | yes | Price per million output tokens (0.0 for local) |
| `max_context_tokens` | int | yes | Maximum context window size |
| `enabled` | bool | yes | Whether this provider is active for routing |

**Validation rules**:
- `name` must be unique across all providers
- `input_price` and `output_price` must be >= 0.0
- If `category` is `local`, `api_key_env` must be null and prices must be 0.0
- `base_url` must be a valid URL

### TaskType (Enum)

Categories for request classification.

| Value | Description |
|-------|-------------|
| `reasoning` | Logic puzzles, proofs, abstract reasoning |
| `knowledge_work` | Business analysis, strategy, expert evaluation |
| `code` | Code generation, debugging, refactoring |
| `extraction` | Summarization, translation, data extraction |
| `creative` | Creative writing, brainstorming |
| `general` | Anything not matching above categories |

### ClassificationResult

Output of the task classifier for a single request.

| Field | Type | Description |
|-------|------|-------------|
| `task_type` | TaskType | Classified task category |
| `complexity` | float | 0.0 (trivial) to 1.0 (frontier-hard) |
| `token_estimate` | int | Estimated input token count |
| `requires_tools` | bool | Whether structured output / tool use is needed |
| `factuality_risk` | bool | Whether factual accuracy is critical |

### RoutingDecision

Output of the decision engine.

| Field | Type | Description |
|-------|------|-------------|
| `selected_model` | string | Provider name chosen for this request |
| `fallback_chain` | list[string] | Ordered fallback providers if selected is unavailable |
| `reason` | string | Human-readable explanation of routing choice |

### RequestRecord

Complete record of a processed request.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Unique request identifier |
| `timestamp` | datetime | When the request was received |
| `messages` | list[dict] | Input messages |
| `classification` | ClassificationResult | How the request was classified |
| `routing` | RoutingDecision | Which model was chosen and why |
| `model_used` | string | Actual model that served the response (may differ from selected if fallback triggered) |
| `response` | string | Model response text |
| `input_tokens` | int | Estimated or actual input token count |
| `output_tokens` | int | Estimated or actual output token count |
| `cost` | float | Computed cost in USD |
| `latency_ms` | int | Total request latency in milliseconds |
| `router_overhead_ms` | int | Classification + routing decision time |
| `cache_hit` | bool | Whether response came from semantic cache |
| `fallback_triggered` | bool | Whether a fallback model was used |

### RoutingRule

A single rule in the decision engine.

| Field | Type | Description |
|-------|------|-------------|
| `task_type` | TaskType | Which task type this rule applies to |
| `complexity_min` | float | Minimum complexity threshold (inclusive) |
| `complexity_max` | float | Maximum complexity threshold (inclusive) |
| `target_model` | string | Provider name to route to |
| `fallback_chain` | list[string] | Ordered fallbacks |
| `priority` | int | Rule evaluation order (lower = higher priority) |

**Evaluation logic**: Rules are evaluated in priority order. First matching rule wins. If no rule matches, the default model (configured globally) is used.

### CalibrationPrompt

A single prompt in the calibration suite.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique prompt identifier |
| `prompt` | string | The prompt text |
| `expected_task_type` | TaskType | What the classifier should assign |
| `expected_best_model` | string | Which model is expected to perform best (null if unknown) |
| `category` | string | Grouping label (e.g., "reasoning", "extraction") |

### CalibrationResult

Aggregated results from running the calibration suite.

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | string (UUID) | Unique calibration run identifier |
| `timestamp` | datetime | When the run was executed |
| `prompts_count` | int | Number of prompts evaluated |
| `models_tested` | list[string] | Which models were included |
| `win_rate_by_task` | dict[TaskType, dict[str, float]] | Per-task-type win rates per model |
| `avg_latency_by_model` | dict[str, float] | Average latency per model in ms |
| `total_cost_by_model` | dict[str, float] | Total cost per model across all prompts |
| `regret_rate` | float | Fraction of requests where router didn't pick the winner |
| `cost_vs_baseline` | float | Cost as percentage of single-model (Sonnet) baseline |

## Relationships

```
Provider 1──* RoutingRule (target_model → Provider.name)
RoutingRule *──* Provider (fallback_chain → Provider.name)
ClassificationResult 1──1 RoutingDecision (classification drives routing)
RequestRecord 1──1 ClassificationResult
RequestRecord 1──1 RoutingDecision
CalibrationPrompt *──1 CalibrationResult (many prompts per run)
```