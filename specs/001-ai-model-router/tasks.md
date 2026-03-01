# Tasks: AI Model Router

**Input**: Design documents from `/specs/001-ai-model-router/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Project initialization and package skeleton

- [x] T001 Create Python package structure with `src/router/__init__.py` and `pyproject.toml` (deps: openai, pydantic, pyyaml, click)
- [x] T002 [P] Create config directory with example files `config/providers.yaml`, `config/routing.yaml`, `config/plugins.yaml`
- [x] T003 [P] Create test directory structure `tests/unit/`, `tests/integration/`, `tests/calibration/` with `tests/conftest.py`
- [x] T004 [P] Configure pytest in `pyproject.toml` (test paths, markers for unit/integration/calibration)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models and configuration infrastructure that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Define ProviderCategory enum and TaskType enum in `src/router/models.py`
- [x] T006 Define Provider Pydantic model in `src/router/models.py` (fields: name, display_name, category, base_url, api_key_env, model_id, input_price, output_price, max_context_tokens, enabled)
- [x] T007 [P] Define ClassificationResult dataclass in `src/router/models.py` (fields: task_type, complexity, token_estimate, requires_tools, factuality_risk)
- [x] T008 [P] Define RoutingDecision dataclass in `src/router/models.py` (fields: selected_model, fallback_chain, reason)
- [x] T009 [P] Define RoutingRule Pydantic model in `src/router/models.py` (fields: task_type, complexity_min, complexity_max, target_model, fallback_chain, priority)
- [x] T010 [P] Define RequestRecord dataclass in `src/router/models.py` (fields: id, timestamp, messages, classification, routing, model_used, response, input_tokens, output_tokens, cost, latency_ms, router_overhead_ms, cache_hit, fallback_triggered)
- [x] T011 [P] Define RequestResult dataclass in `src/router/models.py` (fields: response, model_used, task_type, estimated_cost, latency_ms, cache_hit, fallback_triggered)
- [x] T012 Implement configuration loading in `src/router/config.py` — parse `config/providers.yaml` into list[Provider], validate all fields via Pydantic
- [x] T013 Implement routing config loading in `src/router/config.py` — parse `config/routing.yaml` into list[RoutingRule] with default_model
- [x] T014 [P] Implement plugin config loading in `src/router/config.py` — parse `config/plugins.yaml` into plugin toggle dataclass
- [x] T015 Unit test for all data models in `tests/unit/test_models.py` — validate construction, defaults, validation errors
- [x] T016 Unit test for config loading in `tests/unit/test_config.py` — valid YAML, missing fields, invalid values, Ollama zero-price validation

**Checkpoint**: Foundation ready — all data models defined, config loads and validates. User story implementation can begin.

---

## Phase 3: User Story 1 — Route a Request to the Optimal Model (Priority: P1) 🎯 MVP

**Goal**: Send a prompt, get a response from the best model based on task classification and routing rules

**Independent Test**: Send reasoning, knowledge-work, and extraction prompts. Verify each routes to the expected model (Gemini, Sonnet, Qwen/Ollama) and response includes correct metadata.

### Implementation for User Story 1

- [x] T017 [US1] Implement provider registry in `src/router/providers.py` — load providers from config, store in dict by name, expose `get_provider(name)` and `list_providers()`
- [x] T018 [US1] Implement provider health check in `src/router/providers.py` — HTTP HEAD to base_url with 2-second timeout, return bool
- [x] T019 [US1] Implement `call_model(model_name, messages)` in `src/router/providers.py` — instantiate OpenAI client from provider config, call chat.completions.create, return response content. Raise ProviderUnavailableError on connection failure.
- [x] T020 [US1] Implement task classifier in `src/router/classifier.py` — keyword-based heuristics: match prompt text against keyword sets for each TaskType, compute complexity score (0.0–1.0), detect requires_tools and factuality_risk flags. Return ClassificationResult.
- [x] T021 [US1] Implement decision engine in `src/router/engine.py` — load routing rules from config, evaluate rules in priority order against ClassificationResult, return RoutingDecision with selected_model and fallback_chain
- [x] T022 [US1] Implement fallback logic in `src/router/engine.py` — given a RoutingDecision, try selected_model first, if health check fails walk fallback_chain until a healthy provider is found or all exhausted (raise AllProvidersUnavailableError)
- [x] T023 [US1] Implement full pipeline in `src/router/pipeline.py` — `handle_request(messages)`: classify → route → check health / fallback → call_model → compute cost → build RequestResult → return
- [x] T024 [US1] Unit test for classifier in `tests/unit/test_classifier.py` — test all 6 TaskTypes with at least 3 prompts each, verify complexity ranges, verify requires_tools and factuality_risk detection
- [x] T025 [US1] Unit test for decision engine in `tests/unit/test_engine.py` — test rule matching for each task type/complexity combination, test fallback chain construction, test default model when no rule matches
- [x] T026 [US1] Integration test for pipeline in `tests/integration/test_pipeline.py` — mock provider responses, verify end-to-end: prompt → classification → routing → response with correct metadata

**Checkpoint**: MVP complete. Any prompt can be routed to the best model. Fallback works when a provider is down.

---

## Phase 4: User Story 2 — Register and Manage Model Providers (Priority: P1)

**Goal**: Configure providers across all three categories (cloud, self-hosted, local/Ollama) through YAML config, add/remove without code changes

**Independent Test**: Configure 3 providers (cloud + self-hosted + Ollama), verify all callable. Add a 4th via config only, verify it works.

### Implementation for User Story 2

- [x] T027 [P] [US2] Implement `register_provider(provider)` and `remove_provider(name)` in `src/router/providers.py` — add/remove providers at runtime in the registry
- [x] T028 [P] [US2] Implement Ollama-specific availability detection in `src/router/providers.py` — check if Ollama process is running and target model is loaded, within 2-second timeout
- [x] T029 [US2] Implement `router providers list` CLI command in `src/router/cli.py` — list all providers with name, category, enabled status, health status (✓/✗)
- [x] T030 [US2] Implement `router providers check <name>` CLI command in `src/router/cli.py` — health check a specific provider, print detailed status
- [x] T031 [US2] Integration test for provider management in `tests/integration/test_providers.py` — add provider via config, verify callable, remove via config, verify gone. Test Ollama unavailability fallback.

**Checkpoint**: Providers fully manageable through config. Ollama detected and handled correctly.

---

## Phase 5: User Story 3 — Track and Report Costs (Priority: P2)

**Goal**: Every request produces a cost record. Operator can see spending by model, by task type, and savings vs. single-model baseline.

**Independent Test**: Send 20 requests, query cost data. Verify totals match expected per-model pricing. Verify Ollama shows $0.00. Verify baseline comparison works.

### Implementation for User Story 3

- [x] T032 [US3] Implement cost calculation in `src/router/cost.py` — `compute_cost(input_tokens, output_tokens, provider) -> float` using provider pricing. Ollama returns 0.0.
- [x] T033 [US3] Implement JSON Lines request logging in `src/router/cost.py` — `log_request(record: RequestRecord)` appends to `logs/requests.jsonl`
- [x] T034 [US3] Integrate cost computation and logging into pipeline in `src/router/pipeline.py` — after model call, compute cost, build RequestRecord, log it
- [x] T035 [US3] Implement cost reporting in `src/router/cost.py` — `get_cost_summary(since, until) -> CostSummary` reads from JSONL, aggregates by model and task type, computes baseline_cost (all-Sonnet) and savings_percentage
- [x] T036 [US3] Define CostSummary dataclass in `src/router/models.py` (fields: total_cost, cost_by_model, cost_by_task_type, request_count, baseline_cost, savings_percentage)
- [x] T037 [US3] Implement `router cost` CLI command in `src/router/cli.py` — print cost summary with formatted table
- [x] T038 [US3] Unit test for cost calculation in `tests/unit/test_cost.py` — test cloud pricing, self-hosted pricing, local $0.00 pricing, baseline comparison math

**Checkpoint**: Full cost visibility. Operator sees exactly how routing saves money.

---

## Phase 6: User Story 4 — Classify Requests by Task Type (Priority: P2)

**Goal**: Refine classification accuracy. Operator can debug classification via CLI.

**Independent Test**: Submit 20 calibration prompts, verify 80%+ correct task type assignment.

### Implementation for User Story 4

- [x] T039 [US4] Refine keyword sets in `src/router/classifier.py` — expand keyword lists per TaskType based on testing, add multi-word phrase matching
- [x] T040 [US4] Improve complexity scoring in `src/router/classifier.py` — factor in token length, multi-step instruction detection, domain-specific indicators
- [x] T041 [US4] Implement `router classify "prompt"` CLI command in `src/router/cli.py` — print ClassificationResult (task_type, complexity, flags) without routing
- [x] T042 [US4] Unit test for refined classifier in `tests/unit/test_classifier_refined.py` — 20+ prompts across all 6 TaskTypes, assert 80%+ accuracy, test complexity scoring edge cases

**Checkpoint**: Classifier reliably identifies task type. Operator can debug classification independently.

---

## Phase 7: User Story 5 — Validate Routing with Calibration Suite (Priority: P2)

**Goal**: Run calibration suite to measure routing quality empirically. Report win rate, latency, cost, regret rate.

**Independent Test**: Run calibration with 20 prompts. Verify all 4 metrics computed and reported. Change a rule, re-run, see impact.

### Implementation for User Story 5

- [x] T043 [US5] Create calibration prompts file `config/calibration_prompts.yaml` — 20+ prompts: 4 reasoning, 4 knowledge_work, 4 code, 4 extraction, 2 creative, 2 general, each with expected_task_type
- [x] T044 [US5] Implement calibration runner in `tests/calibration/test_calibration.py` — for each prompt, call all enabled models, collect responses with latency and cost
- [x] T045 [US5] Implement calibration metrics computation in `tests/calibration/test_calibration.py` — compute win_rate_by_task (manual scoring placeholder), avg_latency_by_model, total_cost_by_model, regret_rate, cost_vs_baseline
- [x] T046 [US5] Define CalibrationPrompt and CalibrationResult dataclasses in `src/router/models.py`
- [x] T047 [US5] Implement `router calibrate` CLI command in `src/router/cli.py` — run calibration, print formatted metrics report with before/after comparison support
- [x] T048 [US5] Integration test in `tests/integration/test_calibration.py` — run calibration against at least 2 providers (Ollama + 1 cloud), verify all 4 metrics are populated

**Checkpoint**: Operator can empirically validate routing quality. Data-driven routing rule tuning enabled.

---

## Phase 8: User Story 6 — Semantic Caching (Priority: P3)

**Goal**: Cache responses for semantically equivalent requests. Reduce redundant model calls.

**Independent Test**: Send same request twice, verify second hits cache. Send different request, verify miss.

### Implementation for User Story 6

- [x] T049 [P] [US6] Implement semantic cache in `src/router/cache.py` — in-memory LRU dict, key by request text hash (exact match for v1), configurable max_entries
- [x] T050 [US6] Integrate cache into pipeline in `src/router/pipeline.py` — check cache before classify/route/call. If hit, return cached response with cache_hit=true. If miss, proceed normally and store result.
- [x] T051 [US6] Add cache hit tracking to cost reporting in `src/router/cost.py` — track cache_hit_rate in CostSummary
- [x] T052 [US6] Implement cache toggle via `config/plugins.yaml` — respect enabled flag, configurable similarity_threshold and max_entries
- [x] T053 [US6] Unit test for cache in `tests/unit/test_cache.py` — test hit, miss, eviction, toggle disable
- [x] T054 [US6] Integration test in `tests/integration/test_cache.py` — send duplicate requests, verify cost reduction

**Checkpoint**: Cache reduces redundant calls. Cost savings compound with routing savings.

---

## Phase 9: User Story 7 — Safety Plugins (Priority: P3)

**Goal**: Pre-routing filter chain for jailbreak detection, PII redaction, prompt injection resistance. Each independently toggleable.

**Independent Test**: Submit jailbreak prompt, verify blocked. Submit PII-containing prompt, verify redacted. Disable plugin, verify pass-through.

### Implementation for User Story 7

- [x] T055 [P] [US7] Implement plugin base interface in `src/router/plugins/base.py` — abstract `check(messages) -> PluginResult` with pass/block/sanitize outcomes
- [x] T056 [P] [US7] Implement `src/router/plugins/__init__.py` — plugin chain loader from config, execute plugins in order
- [x] T057 [US7] Implement jailbreak detection plugin in `src/router/plugins/jailbreak.py` — pattern matching against known jailbreak patterns, return block result with reason
- [x] T058 [US7] Implement PII redaction plugin in `src/router/plugins/pii.py` — regex-based detection of emails, phone numbers, SSNs; replace with placeholders; return sanitized messages
- [x] T059 [US7] Integrate plugin chain into pipeline in `src/router/pipeline.py` — run enabled plugins before classification. If blocked, return error. If sanitized, continue with sanitized messages.
- [x] T060 [US7] Unit test for each plugin in `tests/unit/test_plugins.py` — test jailbreak detection (known patterns), PII redaction (email, phone), toggle disable
- [x] T061 [US7] Integration test in `tests/integration/test_plugins.py` — verify plugin chain blocks/sanitizes correctly in full pipeline

**Checkpoint**: Safety filters catch prompt-level risks before any model call.

---

## Phase 10: User Story 8 — Hallucination Detection & Re-Routing (Priority: P3)

**Goal**: Detect low-confidence outputs and optionally re-route to a higher-quality model.

**Independent Test**: Trigger hallucination detector on a low-quality response, verify re-routing to a better model.

### Implementation for User Story 8

- [x] T062 [US8] Implement hallucination detection plugin in `src/router/plugins/hallucination.py` — confidence scoring heuristic (check for hedging language, contradictions, unsupported claims). Return confidence score (0.0–1.0).
- [x] T063 [US8] Implement re-routing logic in `src/router/pipeline.py` — if hallucination plugin flags low confidence and reroute_on_low_confidence is enabled, re-send request to reroute_target model from config
- [x] T064 [US8] Add confidence metadata to RequestResult in `src/router/models.py` — optional confidence field
- [x] T065 [US8] Unit test for hallucination detection in `tests/unit/test_hallucination.py` — test confidence scoring with known low/high confidence responses
- [x] T066 [US8] Integration test in `tests/integration/test_hallucination.py` — verify re-routing triggers when confidence is low, verify improved response returned

**Checkpoint**: Quality safety net catches low-confidence outputs.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Consolidation, hardening, and validation

- [x] T067 Consolidate CLI entry point in `src/router/cli.py` — register all subcommands (route, providers, cost, calibrate, classify), add `--help` documentation, add `--config-dir` option
- [x] T068 [P] Error handling hardening across `src/router/pipeline.py` — handle connection errors, API errors, malformed responses, empty responses with retry-then-fallback
- [x] T069 [P] Error handling for missing/invalid config in `src/router/config.py` — clear error messages for missing files, invalid YAML, missing required fields
- [x] T070 Run full calibration suite and document baseline metrics in `specs/001-ai-model-router/calibration-baseline.md`
- [x] T071 Run quickstart.md validation — follow all steps on a clean environment, document any corrections needed
- [x] T072 Final Constitution compliance review — verify all 7 principles against implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1 Routing (Phase 3)**: Depends on Phase 2
- **US2 Provider Mgmt (Phase 4)**: Depends on Phase 2. Can run in PARALLEL with Phase 3.
- **US3 Cost Tracking (Phase 5)**: Depends on Phase 3 (needs pipeline producing RequestRecords)
- **US4 Classification (Phase 6)**: Depends on Phase 3 (refinement of existing classifier)
- **US5 Calibration (Phase 7)**: Depends on Phase 3 + Phase 5 (needs pipeline + cost tracking)
- **US6 Caching (Phase 8)**: Depends on Phase 3. Can run in PARALLEL with Phases 5–7.
- **US7 Safety (Phase 9)**: Depends on Phase 3. Can run in PARALLEL with Phases 5–8.
- **US8 Hallucination (Phase 10)**: Depends on Phase 3. Can run in PARALLEL with Phases 5–9.
- **Polish (Phase 11)**: Depends on all previous phases

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — no dependencies on other stories
- **US2 (P1)**: After Phase 2 — no dependencies on other stories. PARALLEL with US1.
- **US3 (P2)**: After US1 — needs pipeline
- **US4 (P2)**: After US1 — refines classifier from US1. PARALLEL with US3.
- **US5 (P2)**: After US1 + US3 — needs pipeline + cost data
- **US6 (P3)**: After US1 — PARALLEL with US3–US5
- **US7 (P3)**: After US1 — PARALLEL with US3–US6
- **US8 (P3)**: After US1 — PARALLEL with US3–US7

### Within Each User Story

- Models before services
- Services before endpoints/CLI
- Core implementation before integration
- Story complete before moving to next priority (unless running parallel)

### Parallel Opportunities

- Phase 1: T002, T003, T004 can run in parallel
- Phase 2: T007, T008, T009, T010, T011 can run in parallel; T014 parallel with T012/T013
- Phase 3: T024, T025 (tests) can run in parallel
- Phase 4: T027, T028 can run in parallel
- Phase 8: T049 can run in parallel with other P3 setup
- Phase 9: T055, T056 can run in parallel
- Phase 11: T068, T069 can run in parallel
- Cross-phase: US1 + US2 can run in parallel after Phase 2
- Cross-phase: US3 + US4 can run in parallel after US1
- Cross-phase: US6, US7, US8 can all run in parallel after US1

---

## Parallel Example: User Stories 1 + 2 (after Phase 2)

```bash
# Developer A: User Story 1 (Routing Pipeline)
Task: T017 [US1] Provider registry in src/router/providers.py
Task: T020 [US1] Task classifier in src/router/classifier.py
Task: T021 [US1] Decision engine in src/router/engine.py
Task: T023 [US1] Full pipeline in src/router/pipeline.py

# Developer B: User Story 2 (Provider Management) — in parallel
Task: T027 [US2] register/remove provider in src/router/providers.py  # coordinate with Dev A on providers.py
Task: T029 [US2] CLI providers list in src/router/cli.py
Task: T030 [US2] CLI providers check in src/router/cli.py
```

## Parallel Example: P3 Features (after US1)

```bash
# Developer A: Caching (US6)
Task: T049 [US6] Semantic cache in src/router/cache.py
Task: T050 [US6] Integrate into pipeline

# Developer B: Safety Plugins (US7)
Task: T055 [US7] Plugin base in src/router/plugins/base.py
Task: T057 [US7] Jailbreak in src/router/plugins/jailbreak.py
Task: T058 [US7] PII in src/router/plugins/pii.py

# Developer C: Hallucination (US8)
Task: T062 [US8] Detection in src/router/plugins/hallucination.py
Task: T063 [US8] Re-routing in src/router/pipeline.py  # coordinate with Dev A on pipeline.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (Route Requests)
4. **STOP and VALIDATE**: Route reasoning, knowledge-work, and extraction prompts. Verify correct model selection and fallback.
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 (Routing) → Test independently → **MVP!**
3. Add US2 (Provider Mgmt) → Test independently → Full provider control
4. Add US3 (Cost Tracking) → Test independently → Cost visibility
5. Add US4 (Classification) → Test independently → Improved routing accuracy
6. Add US5 (Calibration) → Test independently → Empirical validation
7. Add US6–US8 (P3 features) → Test independently → Production hardening
8. Polish → Final validation → Production ready

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Total tasks: 72