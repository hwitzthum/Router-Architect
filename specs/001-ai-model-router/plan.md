# Implementation Plan: AI Model Router

**Branch**: `001-ai-model-router` | **Date**: 2026-02-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-ai-model-router/spec.md`

## Summary

Build a production-ready multi-model routing system that classifies each LLM request by task type and complexity, then routes it to the optimal model across cloud APIs (Claude Sonnet 4.6, Gemini 3.1 Pro), self-hosted endpoints (Qwen 3.5 via vLLM), and local models (Ollama). The system provides unified ingress, cost tracking, calibration-based validation, and pluggable cross-cutting concerns (caching, safety, hallucination detection).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: openai (unified client), pydantic (config validation), pyyaml (config files), click (CLI)
**Storage**: JSON Lines file for cost/request logs (no database)
**Testing**: pytest with calibration suite (20+ diverse prompts)
**Target Platform**: Linux/macOS server or workstation
**Project Type**: Library + CLI
**Performance Goals**: Router overhead < 50ms per request; provider health check < 2s
**Constraints**: Must work with only local Ollama models (no cloud keys required for basic operation)
**Scale/Scope**: Single-process deployment; 4 model providers initially

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Route, Never Lock-In | ✅ PASS | All requests flow through decision engine. 4 providers across 3 categories. |
| II. Unified Ingress Interface | ✅ PASS | Single `call_model()` function via OpenAI SDK for all providers including Ollama. |
| III. Signal-Based Classification | ✅ PASS | Classifier extracts TaskType, complexity, token_estimate, requires_tools, factuality_risk. |
| IV. Cost-Aware Decision Engine | ✅ PASS | Three-tier pricing (cloud/self-hosted/local). Cost tracked per request. Ollama at $0.00. |
| V. Test-First, Empirical Validation | ✅ PASS | Calibration suite with 20+ prompts. Four metrics: win rate, latency, cost, regret rate. |
| VI. Production Cross-Cutting Concerns | ✅ PASS | Pluggable cache, safety, hallucination detection. Ollama health tracking. All toggleable. |
| VII. Simplicity and Incrementalism | ✅ PASS | Keyword-based classifier first. P1→P2→P3 priority ordering. No premature abstractions. |

**Post-design re-check**: All gates still pass. No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/001-ai-model-router/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: research decisions
├── data-model.md        # Phase 1: entity definitions
├── quickstart.md        # Phase 1: getting started guide
├── contracts/
│   └── api.md           # Phase 1: API and config contracts
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2: task breakdown (via /speckit.tasks)
```

### Source Code (repository root)

```text
src/router/
├── __init__.py          # Package init, version
├── models.py            # Pydantic data models (Provider, ClassificationResult, etc.)
├── providers.py         # Provider registry, health checks, unified call_model()
├── classifier.py        # Task classification (keyword heuristics)
├── engine.py            # Decision engine (routing rules, fallback chains)
├── cost.py              # Cost tracking, logging, reporting
├── cache.py             # Semantic caching (P3)
├── plugins/             # Safety plugins (P3)
│   ├── __init__.py
│   ├── base.py          # Plugin interface
│   ├── jailbreak.py     # Jailbreak detection
│   ├── pii.py           # PII redaction
│   └── hallucination.py # Hallucination detection + re-routing
├── config.py            # YAML config loading → Pydantic validation
├── pipeline.py          # Full handle_request() pipeline
└── cli.py               # Click CLI entry point

config/
├── providers.yaml       # Provider definitions
├── routing.yaml         # Routing rules
└── plugins.yaml         # Plugin toggles

tests/
├── unit/
│   ├── test_models.py
│   ├── test_classifier.py
│   ├── test_engine.py
│   ├── test_cost.py
│   └── test_config.py
├── integration/
│   ├── test_providers.py
│   ├── test_pipeline.py
│   └── test_fallback.py
├── calibration/
│   ├── prompts.yaml     # 20+ calibration prompts
│   └── test_calibration.py
└── conftest.py
```

**Structure Decision**: Single project layout. The router is a Python library with CLI. No frontend, no web server, no database. All state persisted to JSON Lines log files. This is the simplest structure that satisfies all requirements.

## Implementation Phases

### Phase 1: Setup

- Initialize Python package with pyproject.toml (dependencies: openai, pydantic, pyyaml, click)
- Create `src/router/` package skeleton with `__init__.py`
- Create `config/` directory with example YAML files
- Create `tests/` directory with conftest.py
- Configure pytest

### Phase 2: Foundational (Blocking Prerequisites)

**All user stories depend on these components.**

- **T001**: Define Pydantic data models in `src/router/models.py` — Provider, ProviderCategory, TaskType, ClassificationResult, RoutingDecision, RequestRecord, RoutingRule (from data-model.md)
- **T002**: Implement configuration loading in `src/router/config.py` — parse providers.yaml, routing.yaml, plugins.yaml into validated Pydantic models
- **T003**: Implement provider registry in `src/router/providers.py` — register providers from config, health check (HTTP HEAD with 2s timeout), unified `call_model()` via OpenAI SDK
- **T004**: Unit tests for models, config loading, and provider registry

**Checkpoint**: Can load config, register providers, and call any single model through the unified interface.

### Phase 3: User Story 1 — Route Requests (P1) 🎯 MVP

- **T005**: Implement task classifier in `src/router/classifier.py` — keyword-based heuristic classification returning ClassificationResult
- **T006**: Implement decision engine in `src/router/engine.py` — evaluate routing rules from config, select model, build fallback chain
- **T007**: Implement fallback logic in engine — try primary, detect unavailability, walk fallback chain
- **T008**: Implement full pipeline in `src/router/pipeline.py` — classify → route → call → return RequestResult
- **T009**: Unit tests for classifier (20 prompts covering all TaskTypes)
- **T010**: Unit tests for engine (routing rule matching, fallback chain)
- **T011**: Integration test: end-to-end pipeline with mock providers

**Checkpoint**: Can route any request to the correct model. Fallbacks work when a model is unavailable. MVP complete.

### Phase 4: User Story 2 — Provider Management (P1)

- **T012**: Implement provider CRUD operations — add/update/remove providers at runtime via registry
- **T013**: Implement `router providers list` and `router providers check` CLI commands
- **T014**: Integration test: add a new Ollama model via config, verify it's routable

**Checkpoint**: Providers can be managed through configuration. Ollama models work as first-class providers.

### Phase 5: User Story 3 — Cost Tracking (P2)

- **T015**: Implement cost calculation in `src/router/cost.py` — per-request cost from token estimates and provider pricing
- **T016**: Implement JSON Lines logging — append RequestRecord to log file after each request
- **T017**: Implement cost reporting — aggregate from log file, compute cost_by_model, cost_by_task_type, baseline comparison
- **T018**: Implement `router cost` CLI command
- **T019**: Unit tests for cost calculation (cloud, self-hosted, local at $0.00)

**Checkpoint**: Every request is logged with cost. Operator can see spending breakdown and savings vs. single-model baseline.

### Phase 6: User Story 4 — Classification Quality (P2)

- **T020**: Refine classifier keyword sets based on initial testing
- **T021**: Add complexity scoring logic (multi-step detection, token length influence)
- **T022**: Implement `router classify` CLI command for debugging
- **T023**: Unit tests for refined classification across all 6 TaskTypes

**Checkpoint**: Classifier correctly identifies task type for 80%+ of calibration prompts.

### Phase 7: User Story 5 — Calibration Suite (P2)

- **T024**: Create calibration prompts file `config/calibration_prompts.yaml` with 20+ diverse prompts
- **T025**: Implement calibration runner in `tests/calibration/test_calibration.py` — run all prompts against all models, collect outputs
- **T026**: Implement metrics computation — win rate by task class, avg latency, total cost, regret rate, baseline comparison
- **T027**: Implement `router calibrate` CLI command with formatted report output
- **T028**: Integration test: run calibration against at least 2 real providers

**Checkpoint**: Operator can validate routing quality empirically. Four metrics reported.

### Phase 8: User Story 6 — Semantic Caching (P3)

- **T029**: Implement semantic cache in `src/router/cache.py` — embedding-based similarity with LRU eviction
- **T030**: Integrate cache as pre-routing step in pipeline (check cache before classify/route/call)
- **T031**: Add cache_hit tracking to RequestRecord and cost reporting
- **T032**: Unit tests for cache hit/miss/eviction
- **T033**: Integration test: verify cache reduces cost on repeated requests

**Checkpoint**: Cache reduces redundant model calls on repetitive workloads.

### Phase 9: User Story 7 — Safety Plugins (P3)

- **T034**: Implement plugin base interface in `src/router/plugins/base.py` — `check(messages) → pass | block | sanitize`
- **T035**: Implement jailbreak detection plugin
- **T036**: Implement PII redaction plugin
- **T037**: Integrate plugins as pre-routing filter chain in pipeline
- **T038**: Unit tests for each plugin independently
- **T039**: Integration test: verify plugin chain blocks/sanitizes correctly

**Checkpoint**: Safety plugins catch prompt-level risks before model calls.

### Phase 10: User Story 8 — Hallucination Detection (P3)

- **T040**: Implement hallucination detection plugin in `src/router/plugins/hallucination.py`
- **T041**: Implement re-routing logic — when low confidence detected, re-send to higher-quality model
- **T042**: Unit tests for hallucination detection and re-routing
- **T043**: Integration test: verify re-routing improves response quality

**Checkpoint**: Low-confidence outputs are caught and optionally improved via re-routing.

### Phase 11: Polish & Cross-Cutting

- **T044**: CLI entry point consolidation in `src/router/cli.py` — all subcommands
- **T045**: Error handling hardening across pipeline (connection errors, API errors, malformed responses)
- **T046**: Run full calibration suite and document baseline metrics
- **T047**: Run quickstart.md validation — follow steps on a clean environment
- **T048**: Final code review for Constitution compliance

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (Routing)** + **Phase 4 (Providers)**: Both depend on Phase 2. Can run in parallel. Together they form MVP.
- **Phase 5 (Cost)**: Depends on Phase 3 (needs pipeline producing RequestRecords)
- **Phase 6 (Classification)**: Depends on Phase 3 (refinement of existing classifier)
- **Phase 7 (Calibration)**: Depends on Phase 3 + Phase 5 (needs pipeline + cost tracking)
- **Phase 8–10 (P3 features)**: Depend on Phase 3. Can run in parallel with each other.
- **Phase 11 (Polish)**: Depends on all previous phases

### Parallel Opportunities

- Phase 3 (Routing) and Phase 4 (Providers) can proceed in parallel after Phase 2
- Phase 5 (Cost) and Phase 6 (Classification) can proceed in parallel after Phase 3
- Phase 8, 9, and 10 (all P3) can proceed in parallel after Phase 3
- Within each phase, tasks marked [P] can run in parallel

## Complexity Tracking

> No Constitution Check violations. No complexity justifications needed.