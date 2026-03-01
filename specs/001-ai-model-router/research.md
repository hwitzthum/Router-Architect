# Research: AI Model Router

**Branch**: `001-ai-model-router`
**Date**: 2026-02-28
**Purpose**: Resolve all technical unknowns and document design decisions

## R1: Unified Client Interface for All Provider Categories

**Decision**: Use the OpenAI Python SDK (`openai`) as the single client for all three provider categories.

**Rationale**: All three target providers expose OpenAI-compatible chat-completion APIs:
- **Cloud (Anthropic)**: Anthropic provides an OpenAI-compatible proxy. Alternatively, use the native `anthropic` SDK behind an adapter.
- **Cloud (Google)**: Gemini exposes an OpenAI-compatible endpoint at `https://generativelanguage.googleapis.com/v1beta`.
- **Self-hosted (Qwen via vLLM)**: vLLM natively serves OpenAI-compatible endpoints. The article's code confirms this.
- **Local (Ollama)**: Ollama exposes `http://localhost:11434/v1` as an OpenAI-compatible endpoint.

**Alternatives considered**:
- LiteLLM: Adds a dependency and abstraction layer. Rejected per Constitution Principle VII (simplicity) — the OpenAI SDK already provides the needed unification.
- Per-provider native SDKs with custom adapter: More code to maintain, no benefit since all providers speak the same protocol.

## R2: Task Classification Approach

**Decision**: Start with keyword-based heuristic classification. Plan for embedding-based semantic classification as a future upgrade path.

**Rationale**: The article explicitly recommends starting simple: "Even a keyword-based classifier that routes extraction tasks to Qwen and reasoning tasks to Gemini will show measurable cost savings." Constitution Principle VII mandates incrementalism.

**Implementation approach**:
- Define `TaskType` enum: REASONING, KNOWLEDGE_WORK, CODE, EXTRACTION, CREATIVE, GENERAL
- Fast heuristics: keyword matching against curated keyword sets per task type
- Complexity scoring: token length, presence of multi-step instructions, domain-specific indicators
- Flags: `requires_tools` (structured output keywords), `factuality_risk` (citation/verification keywords)

**Alternatives considered**:
- Embedding-based from day one: Higher accuracy but adds a dependency (embedding model) and latency. Deferred to post-MVP iteration.
- LLM-as-classifier: Using a small model to classify. Adds latency and cost per request. Rejected for v1.

## R3: Configuration Management

**Decision**: Use YAML configuration files for provider registry, pricing, and routing rules. Load via Pydantic models for validation.

**Rationale**: YAML is human-readable and widely used for configuration. Pydantic provides runtime validation, type safety, and clear error messages for misconfiguration. This satisfies Constitution requirements for externalized configuration (Principle IV, Technology Constraints).

**Configuration structure**:
- `config/providers.yaml`: Provider definitions (base URL, API key env var, model ID, pricing, category)
- `config/routing.yaml`: Routing rules (task type → model mappings, complexity thresholds, fallback chains)
- `config/plugins.yaml`: Plugin toggles (caching, safety, hallucination detection)

**Alternatives considered**:
- Environment variables only: Insufficient for structured data like routing rules and provider lists.
- TOML: Less common for complex nested configuration. YAML is more natural for lists and maps.
- JSON: No comments support. YAML preferred for human-edited config.

## R4: Fallback Chain Strategy

**Decision**: Each routing rule specifies an ordered fallback chain. The decision engine tries models in order, skipping unavailable ones.

**Rationale**: Constitution Principle I requires support for local Ollama models which may not always be running. The decision engine must handle this gracefully. The fallback chain also covers cloud API rate limits and outages.

**Fallback logic**:
1. Decision engine selects primary model based on classification
2. If primary is unavailable (health check fails or connection refused), try next in fallback chain
3. Availability check: HTTP HEAD to base URL with 2-second timeout (Constitution requires detection within 2 seconds)
4. If all models in chain unavailable: return error with clear message

**Alternatives considered**:
- Retry with exponential backoff on the same model: Doesn't help if model is genuinely down. Fallback chain provides faster recovery.
- Circuit breaker pattern: Good for long-term unavailability. Can be added later on top of fallback chains.

## R5: Cost Tracking Implementation

**Decision**: Track costs in-memory with periodic flush to a JSON Lines log file. Provide a reporting module that aggregates from the log.

**Rationale**: Simplest approach per Constitution Principle VII. No database dependency for the core router. JSON Lines is append-only, easy to query, and can be ingested by any analytics tool later.

**Cost calculation**:
- Token counts: estimated from request/response text (word count × 1.3 factor) for heuristic tracking; actual counts from API response headers where available
- Cost formula: `(input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price`
- Ollama/local models: cost recorded as $0.00

**Alternatives considered**:
- SQLite database: Adds dependency. JSON Lines is simpler and sufficient for v1.
- In-memory only: Lost on restart. JSON Lines persists cost history.

## R6: Semantic Caching Strategy

**Decision**: Use sentence embeddings (via a lightweight local model or Ollama embedding endpoint) to compute request similarity. Cache in an in-memory dictionary with LRU eviction.

**Rationale**: The article cites 15–30% cache hit rates on repetitive workloads. An embedding-based approach catches semantically equivalent but lexically different requests. Ollama can serve embedding models locally (zero cost for similarity computation).

**Alternatives considered**:
- Exact string matching: Misses semantically equivalent rephrasings. Too low a hit rate.
- Redis-based cache: External dependency. In-memory LRU is sufficient for single-process deployments in v1.

## R7: Safety Plugins Architecture

**Decision**: Implement safety plugins as a pre-routing filter chain. Each plugin implements a `check(messages) -> (pass | block | sanitize)` interface. Plugins are toggled via configuration.

**Rationale**: Constitution Principle VI requires pluggable, toggleable safety components. A simple filter chain pattern keeps each plugin independently testable.

**Alternatives considered**:
- Monolithic safety check: Not toggleable or extensible. Rejected.
- Post-routing safety (check outputs): Needed too (hallucination detection), but pre-routing catches prompt-level risks before any model is called.

## R8: Project Structure Decision

**Decision**: Single project (Option 1 from plan template). This is a Python library with CLI entry point, not a web application.

**Rationale**: The router is a backend service/library consumed programmatically or via CLI. There is no frontend. A single `src/` tree with clear module separation is sufficient.

**Structure**:
```
src/router/
├── __init__.py
├── models.py          # Pydantic data models (ClassificationResult, Provider, etc.)
├── providers.py       # Provider registry and unified call_model()
├── classifier.py      # Task classification (heuristics + future embeddings)
├── engine.py          # Decision engine (routing rules + fallback chains)
├── cost.py            # Cost tracking and reporting
├── cache.py           # Semantic caching (P3)
├── plugins/           # Safety plugins (P3)
│   ├── __init__.py
│   ├── base.py        # Plugin interface
│   ├── jailbreak.py
│   ├── pii.py
│   └── hallucination.py
├── config.py          # Configuration loading (YAML → Pydantic)
└── cli.py             # CLI entry point

config/
├── providers.yaml
├── routing.yaml
└── plugins.yaml

tests/
├── unit/
├── integration/
├── calibration/
│   ├── prompts.yaml   # 20+ calibration prompts
│   └── run_calibration.py
└── conftest.py
```