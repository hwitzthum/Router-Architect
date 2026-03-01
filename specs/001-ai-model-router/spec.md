# Feature Specification: AI Model Router

**Feature Branch**: `1-ai-model-router`
**Created**: 2026-02-28
**Status**: Draft
**Input**: User description: "Production-ready multi-model routing system based on the Lanham article architecture, supporting Qwen 3.5, Claude Sonnet 4.6, Gemini 3.1 Pro, and local Ollama models"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Route a Request to the Optimal Model (Priority: P1)

An operator sends a natural-language prompt to the router. The router classifies the request by task type and complexity, selects the best model based on routing rules, calls the chosen model, and returns the response along with metadata (model used, task type, estimated cost).

**Why this priority**: This is the entire reason the system exists. Without per-request routing, there is no product.

**Independent Test**: Send a reasoning prompt ("Solve this logic puzzle…"), a knowledge-work prompt ("Evaluate this business strategy…"), and an extraction prompt ("Summarize this paragraph…"). Verify each is routed to the expected model (Gemini, Sonnet, Qwen/Ollama respectively) and the response is returned with correct metadata.

**Acceptance Scenarios**:

1. **Given** a prompt containing reasoning keywords (solve, puzzle, logic, prove) with complexity > 0.6, **When** the request is submitted, **Then** the router selects Gemini and returns a response with `model_used: "gemini"`.
2. **Given** a prompt about business analysis or strategy, **When** the request is submitted, **Then** the router selects Sonnet and returns a response with `model_used: "sonnet"`.
3. **Given** a simple extraction or summarization prompt with complexity < 0.5, **When** the request is submitted, **Then** the router selects the most cost-effective model (Qwen or local Ollama) and returns a response with the appropriate `model_used`.
4. **Given** a coding prompt with high complexity (> 0.7), **When** the request is submitted, **Then** the router selects Gemini; for lower complexity coding tasks it selects Qwen or a local model.
5. **Given** any prompt that does not match a specific category, **When** the request is submitted, **Then** the router defaults to Sonnet.

---

### User Story 2 - Register and Manage Model Providers (Priority: P1)

An operator configures the system with model providers across three categories: cloud APIs (Anthropic, Google), self-hosted endpoints (Qwen via vLLM), and local models (Ollama). Each provider is registered with its base URL, API key (if needed), pricing, and model ID. The operator can add, update, or remove providers through configuration without changing code.

**Why this priority**: Without provider registration, no models can be called. This is foundational infrastructure that all other stories depend on.

**Independent Test**: Configure three providers (one cloud, one self-hosted, one Ollama local), verify each can be called through the unified interface, then add a fourth provider via configuration only and confirm it works without code changes.

**Acceptance Scenarios**:

1. **Given** a provider configuration entry for Claude with base URL, API key, and pricing, **When** the system starts, **Then** Claude is available as a routing target.
2. **Given** a provider configuration entry for an Ollama model with base URL `http://localhost:11434/v1` and zero pricing, **When** the system starts, **Then** the Ollama model is available as a routing target.
3. **Given** a new model provider added to the configuration file, **When** the system is restarted (or config reloaded), **Then** the new model is available for routing without any code changes.
4. **Given** a local Ollama model that is not currently running, **When** a request would normally route to it, **Then** the system detects unavailability and falls back to the next provider in the fallback chain.

---

### User Story 3 - Track and Report Costs Per Request (Priority: P2)

An operator reviews cost data to understand spending patterns across models and task types. Every request produces a cost record with input tokens, output tokens, model used, provider category (cloud/self-hosted/local), task type, and computed cost. The operator can query aggregate cost data to see total spend by model, by task type, and projected savings from routing compared to a single-model baseline.

**Why this priority**: Cost optimization is the primary economic justification for routing. Without cost tracking, operators cannot validate that routing is saving money.

**Independent Test**: Send 20 requests spanning different task types, then query cost data. Verify total cost matches expected per-model pricing. Verify the system can compute "what would this have cost on a single Sonnet deployment" as a baseline comparison.

**Acceptance Scenarios**:

1. **Given** a completed request, **When** the response is returned, **Then** the response metadata includes `estimated_cost` broken down by input and output tokens at the selected model's pricing.
2. **Given** a request routed to a local Ollama model, **When** cost is computed, **Then** the token cost is recorded as $0.00 (zero marginal cost).
3. **Given** 100 completed requests over a period, **When** the operator queries cost data, **Then** the system returns aggregated costs by model, by task type, and the total.
4. **Given** aggregated cost data, **When** the operator requests a savings comparison, **Then** the system calculates what the same requests would have cost using only Sonnet and shows the percentage reduction.

---

### User Story 4 - Classify Requests by Task Type and Complexity (Priority: P2)

The system classifies each incoming request into a task type (reasoning, knowledge_work, code, extraction, creative, general) and assigns a complexity score (0.0–1.0). Classification uses fast heuristics (keyword matching, token estimation, tool detection) initially, with a path to embedding-based semantic classification later.

**Why this priority**: Classification quality directly determines routing quality. Poor classification leads to suboptimal model selection, wasting both money and response quality.

**Independent Test**: Submit 20 calibration prompts with known expected task types. Verify the classifier assigns the correct task type to at least 80% of them.

**Acceptance Scenarios**:

1. **Given** a prompt containing "solve", "puzzle", "logic", or "prove", **When** classified, **Then** the task type is `reasoning` with complexity >= 0.7.
2. **Given** a prompt containing "extract", "summarize", or "translate", **When** classified, **Then** the task type is `extraction` with complexity <= 0.4.
3. **Given** a prompt containing "code", "function", "debug", or "refactor", **When** classified, **Then** the task type is `code`.
4. **Given** a prompt requesting JSON output or structured extraction, **When** classified, **Then** `requires_tools` is set to true.
5. **Given** a prompt asking for factual verification or citing sources, **When** classified, **Then** `factuality_risk` is set to true.

---

### User Story 5 - Validate Routing Quality with Calibration Suite (Priority: P2)

An operator runs a calibration suite of 20+ diverse prompts to measure routing quality. For each prompt, the system runs all configured models, scores outputs (manually or via automated eval), and reports four metrics: win rate by task class, latency distribution, cost per request, and regret rate. This validates whether the router is making good decisions on the operator's actual workload.

**Why this priority**: Without empirical validation, routing rules are just guesses. The calibration suite is the mechanism that turns the router from a prototype into a production system.

**Independent Test**: Run the calibration suite with the default 20 prompts. Verify all four metrics are computed and reported. Change a routing rule, re-run, and verify the metrics show the impact.

**Acceptance Scenarios**:

1. **Given** a calibration set of 20 prompts spanning reasoning, code, extraction, knowledge work, and creative tasks, **When** the calibration suite runs, **Then** each prompt is sent to all configured models and outputs are collected.
2. **Given** collected calibration outputs, **When** scoring is complete, **Then** the system reports win rate per task class (which model won most often for each task type).
3. **Given** calibration results, **When** the operator views the report, **Then** regret rate is shown — the percentage of requests where the router's chosen model was not the best performer.
4. **Given** a routing rule change, **When** calibration is re-run, **Then** the report shows before/after comparison of all four metrics.

---

### User Story 6 - Semantic Caching for Repeated Requests (Priority: P3)

The system caches responses for semantically equivalent requests. When a new request is semantically similar to a cached one (above a configurable similarity threshold), the cached response is returned immediately without calling any model. Cache hit rate is tracked as a metric.

**Why this priority**: Caching is the "easiest cost win" per the article. On repetitive workloads (e.g., customer support), cache hit rates of 15–30% are common, compounding routing savings.

**Independent Test**: Send the same request twice; verify the second returns from cache. Send a semantically similar (but not identical) request; verify it also hits cache if above the similarity threshold. Send a semantically different request; verify it misses cache.

**Acceptance Scenarios**:

1. **Given** a request identical to a previously-answered one, **When** submitted, **Then** the cached response is returned without calling any model, and the response metadata indicates `cache_hit: true`.
2. **Given** a request semantically similar to a cached request (above configurable threshold), **When** submitted, **Then** the cached response is returned.
3. **Given** caching is enabled, **When** 1000 requests have been processed, **Then** the system reports cache hit rate as a percentage.
4. **Given** the operator disables caching via configuration, **When** requests are submitted, **Then** all requests go directly to models (caching is toggleable).

---

### User Story 7 - Safety Plugins (Pre-Routing Filters) (Priority: P3)

The system applies configurable safety filters before routing: jailbreak detection, PII redaction, and prompt injection resistance. Each plugin is independently toggleable. Flagged requests are either blocked, sanitized, or logged depending on plugin configuration.

**Why this priority**: Safety is a production cross-cutting concern. It protects the system from misuse and ensures compliance, but the core routing value works without it.

**Independent Test**: Submit a prompt containing a known jailbreak pattern; verify it is blocked or flagged. Submit a prompt containing PII (email, phone); verify PII is redacted before the prompt reaches the model.

**Acceptance Scenarios**:

1. **Given** a prompt containing a known jailbreak pattern, **When** safety plugins are enabled, **Then** the request is blocked and the operator is notified.
2. **Given** a prompt containing personal email addresses, **When** PII redaction is enabled, **Then** emails are replaced with placeholders before the prompt reaches any model.
3. **Given** the operator disables a specific safety plugin, **When** a request that would trigger it is submitted, **Then** the request passes through unfiltered (plugins are independently toggleable).

---

### User Story 8 - Hallucination Detection and Re-Routing (Priority: P3)

The system detects model outputs with low factual confidence and flags them for secondary review or re-routing to a more capable model. When a response is flagged, the system can optionally re-send the request to a higher-quality model and return the improved response.

**Why this priority**: Hallucination detection catches quality failures that routing alone cannot prevent. It's a quality safety net that matters most for factuality-critical tasks.

**Independent Test**: Submit a factual question to a lower-quality model; trigger the hallucination detector; verify the request is automatically re-routed to a higher-quality model and the improved response is returned.

**Acceptance Scenarios**:

1. **Given** a response flagged as low-confidence by the hallucination detector, **When** re-routing is enabled, **Then** the request is re-sent to a higher-quality model and the improved response is returned.
2. **Given** a response flagged as low-confidence, **When** re-routing is disabled, **Then** the response is returned with a `confidence: low` flag in metadata for the operator to act on.
3. **Given** hallucination detection is disabled via configuration, **When** any response is returned, **Then** no confidence checking occurs (the plugin is toggleable).

---

### Edge Cases

- What happens when all configured cloud providers are down or rate-limited? The system MUST fall back to local Ollama models if available, or return a clear error with retry guidance.
- What happens when the Ollama process is not running? The system MUST detect unavailability within 2 seconds and fall back to the next provider in the chain.
- What happens when a prompt is extremely long (approaching a model's context window)? The classifier MUST estimate token count and route only to models whose context window accommodates the input.
- What happens when a model returns an empty or malformed response? The system MUST retry with the same model once, then fall back to an alternative model.
- What happens when pricing configuration is missing for a model? The system MUST refuse to route to that model and log a warning, preventing untracked cost.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST route each incoming request to a model selected by the decision engine based on task classification and cost signals.
- **FR-002**: System MUST support three provider categories: cloud API, self-hosted (vLLM/SGLang), and local (Ollama) — all accessed through one unified OpenAI-compatible interface.
- **FR-003**: System MUST classify each request by task type (reasoning, knowledge_work, code, extraction, creative, general), complexity (0.0–1.0), estimated token count, tool requirement, and factuality risk.
- **FR-004**: System MUST track cost per request (input tokens, output tokens, model pricing) and aggregate costs by model and task type.
- **FR-005**: System MUST support fallback chains when a selected model is unavailable (e.g., Ollama not running → fall back to cloud equivalent).
- **FR-006**: System MUST allow adding new model providers through configuration only, without code changes to the routing pipeline.
- **FR-007**: System MUST support a calibration suite that runs all models against a prompt set and reports win rate, latency, cost, and regret rate.
- **FR-008**: System MUST support pluggable cross-cutting concerns (semantic caching, safety filters, hallucination detection) as toggleable components.
- **FR-009**: System MUST externalize all routing rules, pricing, and provider configuration (not hardcoded).
- **FR-010**: System MUST detect local Ollama model availability within 2 seconds and handle unavailability gracefully.

### Key Entities

- **Provider**: A configured model endpoint with base URL, API key, model ID, pricing (input/output per million tokens), provider category (cloud/self-hosted/local), and health status.
- **ClassificationResult**: Task type, complexity score, estimated token count, requires_tools flag, factuality_risk flag — produced by the classifier for each request.
- **RoutingDecision**: Selected model name, fallback chain, reasoning for selection — produced by the decision engine.
- **RequestRecord**: Full record of a completed request including prompt, response, model used, task classification, token counts, cost, latency, cache hit status.
- **CalibrationResult**: Per-prompt scores across all models, aggregated metrics (win rate, latency distribution, cost, regret rate).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The router correctly routes at least 80% of calibration prompts to the model that produces the best output for that task type (as measured by win rate).
- **SC-002**: Cost per request is reduced by at least 30% compared to routing all traffic to a single Sonnet deployment, on a representative workload mix.
- **SC-003**: Router overhead (classification + decision engine latency) adds less than 50ms to each request.
- **SC-004**: Adding a new model provider requires only configuration changes and takes less than 10 minutes.
- **SC-005**: When a local Ollama model is unavailable, the system falls back to an alternative within 3 seconds with no user-visible error.
- **SC-006**: The calibration suite produces a complete report (all four metrics) in under 30 minutes for 20 prompts across 4 models.
- **SC-007**: Semantic cache achieves at least a 15% hit rate on repetitive workloads, further reducing costs.

## Assumptions

- Operators have API keys for Anthropic and Google Cloud, or will obtain them before deployment.
- Ollama is installed locally on the machine where the router runs (or on a reachable network host).
- Self-hosted Qwen via vLLM is optional; the system works with cloud-only and local-only configurations too.
- The OpenAI Python SDK is used as the unified client for all providers, since all three target provider categories expose OpenAI-compatible APIs.
- Initial classification uses keyword-based heuristics; embedding-based semantic classification is a future enhancement.
- The calibration suite scoring is initially manual (operator grades outputs); automated evaluation is a future enhancement.