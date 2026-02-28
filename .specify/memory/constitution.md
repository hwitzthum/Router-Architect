<!--
Sync Impact Report
- Version change: N/A → 1.0.0 (initial creation)
- Added sections: All (initial constitution)
- Templates requiring updates:
  - .specify/templates/plan-template.md ⚠ pending (not yet customized)
  - .specify/templates/spec-template.md ⚠ pending (not yet customized)
  - .specify/templates/tasks-template.md ⚠ pending (not yet customized)
- Follow-up TODOs: None
-->

# AI Model Router Constitution

## Core Principles

### I. Route, Never Lock-In

Every LLM request MUST be routed through a decision engine to the optimal model for the task at hand. No single model may be hardcoded as the default for all request types. The system MUST support hosted API providers (Anthropic, Google), self-hosted OpenAI-compatible endpoints (vLLM/SGLang serving Qwen), and locally-run models via Ollama. The router MUST be extensible to accommodate new models — whether cloud, self-hosted, or local — within days of their release.

**Rationale**: Benchmark leadership flips between models depending on the task. Locking into one provider means accepting suboptimal performance on entire categories of tasks. Local models via Ollama add a zero-marginal-cost tier for suitable workloads (privacy-sensitive, offline, high-volume low-complexity) that further strengthens the economic case for routing.

### II. Unified Ingress Interface

All model providers MUST be accessed through a single normalized interface. This applies equally to hosted APIs (Gemini, Claude), self-hosted endpoints (vLLM serving Qwen), and local Ollama models. The caller MUST use one request schema in and one response schema out, regardless of provider type.

**Rationale**: Ollama exposes an OpenAI-compatible API at `http://localhost:11434/v1`, making it a drop-in addition to the same unified client interface used for cloud and self-hosted models. No provider-specific branching should exist in application code.

### III. Signal-Based Classification

Every incoming request MUST be classified before routing. Classification MUST extract both fast heuristics (token length, language detection, tool requirements, factuality risk) and semantic signals (task-type embedding similarity). Routing decisions MUST be based on similarity to tasks the system has already measured — not solely on public benchmarks.

**Rationale**: Public benchmarks tell you what a model can do in general. A calibration set tells you what it does on your tasks. The article explicitly warns: "do not route purely off public benchmarks. Route off similarity to tasks you have already measured."

### IV. Cost-Aware Decision Engine

The routing policy MUST factor in per-model token pricing alongside task-quality signals. The cost model MUST account for three pricing tiers:

- **Cloud APIs**: Per-token pricing (e.g., Sonnet at $3/$15, Gemini at $2/$12 per million tokens)
- **Self-hosted**: Infrastructure cost amortized per token (e.g., Qwen via vLLM at $0.60/$3.60)
- **Local/Ollama**: Zero marginal token cost but with latency and quality constraints

When multiple models produce acceptable results for a task category, the router MUST prefer the most cost-effective option. Cost tracking per request MUST be built into the pipeline from day one.

**Rationale**: Local Ollama models have zero per-token cost, making them the optimal choice for high-volume, low-complexity tasks where quality is acceptable — further extending the 46% cost reduction the article demonstrates through cloud-only routing.

### V. Test-First, Empirical Validation

The router is an empirical system. Every routing rule MUST be validated against a calibration set of diverse prompts spanning the actual workload. Four metrics MUST be tracked from day one: (1) win rate by task class, (2) latency distribution (model + router overhead), (3) cost per request, and (4) regret rate (how often the router's choice would be overridden after seeing the output). Local Ollama models MUST be included in calibration benchmarks to establish their quality thresholds per task type.

**Rationale**: A router that picks the "wrong" model by benchmark standards but picks the right model for your specific tasks is doing its job perfectly. Evaluation is about routing correctness on your distribution, not winning a public benchmark.

### VI. Production Cross-Cutting Concerns

The system MUST implement production-ready cross-cutting concerns as pluggable components: semantic caching (for cost reduction on repetitive workloads), safety plugins (jailbreak detection, PII redaction, prompt injection resistance as pre-routing filters), and hallucination detection (flagging low-confidence outputs for secondary review or re-routing). These MUST be toggleable and composable in the signal chain. For local Ollama models, the system MUST additionally track model availability and health, since local models may not always be running.

**Rationale**: A routing layer in production needs more than model selection. Cache hit rates of 15–30% are common on repetitive workloads, compounding routing cost savings. Local models introduce availability as an additional concern that cloud APIs handle transparently.

### VII. Simplicity and Incrementalism

Start with the simplest possible router and iterate. A keyword-based classifier that routes extraction tasks to Qwen (or a local Ollama model) and reasoning tasks to Gemini MUST show measurable cost savings before adding complexity. Avoid premature abstraction — three similar routing rules are better than a premature routing framework.

**Rationale**: The article's "Monday morning" advice is explicit: audit workloads, run a three-model test on 20 representative prompts, then build the simplest router that shows savings. Complexity is added only when validated by empirical results.

## Architecture Layers

The system MUST be composed of four distinct layers, each independently testable and deployable:

1. **Ingress Normalization** — Unified client interface wrapping all model providers (cloud APIs, self-hosted vLLM, local Ollama) behind a single `call_model(model_name, messages)` function. Provider configuration (base URLs, API keys, availability checks) is managed through a registry.
2. **Task Classifier** — Extracts `TaskType`, `complexity`, `token_estimate`, `requires_tools`, and `factuality_risk` from each request using fast heuristics and semantic signals.
3. **Decision Engine** — Maps classification signals to model choices with cost awareness. Routing rules anchor to measured performance data (e.g., Gemini for reasoning, Sonnet for knowledge work, Qwen/Ollama for cost-sensitive volume). The engine MUST support fallback chains (e.g., try Ollama local → fall back to Qwen cloud if local model unavailable or quality threshold not met).
4. **Cost Tracker** — Records input/output token counts and costs per request, broken down by model, provider type (cloud/self-hosted/local), and task type.

## Model Provider Categories

The router MUST support these provider categories as first-class citizens:

| Category | Examples | Interface | Cost Model |
|---|---|---|---|
| Cloud API | Claude (Anthropic), Gemini (Google) | OpenAI-compatible SDK | Per-token billing |
| Self-hosted | Qwen 3.5 via vLLM/SGLang | OpenAI-compatible endpoint | Infrastructure-amortized |
| Local | Any model via Ollama | OpenAI-compatible at localhost:11434 | Zero marginal cost |

Adding a new provider in any category MUST require only a configuration entry (base URL, API key or none, pricing, model ID) — no changes to core routing logic.

## Technology Constraints

- **Language**: Python 3.11+
- **API Client**: OpenAI SDK (unified interface for cloud, self-hosted, and Ollama providers)
- **Self-hosted serving**: vLLM or SGLang for Qwen 3.5 (OpenAI-compatible endpoint)
- **Local serving**: Ollama (OpenAI-compatible endpoint at localhost:11434/v1)
- **Testing**: pytest with a calibration set of minimum 20 diverse prompts
- **Configuration**: Model pricing, routing rules, provider endpoints, and Ollama model names MUST be externalized (not hardcoded)
- **Extensibility**: Adding a new model provider MUST require only configuration changes plus an optional classifier update — no changes to the core routing pipeline

## Development Workflow

- All routing rules MUST have corresponding test cases in the calibration set
- Routing changes MUST be validated by running the full calibration suite and comparing win rate, cost, and regret rate before and after
- New model integrations (including Ollama models) MUST include: provider client configuration, pricing entry (zero for local), quality profile from calibration, and at least 5 calibration prompts exercising the model's strengths
- Cost projections MUST be computed before deploying routing rule changes to production
- Local Ollama models MUST be tested for availability handling (graceful fallback when model is not running)

## Governance

- This constitution supersedes ad-hoc model selection decisions. All model routing logic MUST flow through the decision engine.
- Amendments require: (1) a documented rationale referencing empirical data, (2) updated calibration results, and (3) a migration plan if routing rules change.
- All PRs touching routing logic MUST include calibration suite results demonstrating no regression in win rate or cost efficiency.
- Complexity additions MUST be justified by measured improvement on the calibration set.

**Version**: 1.0.0 | **Ratified**: 2026-02-28 | **Last Amended**: 2026-02-28