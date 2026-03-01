# AI Model Router

Production-ready multi-model LLM routing system with a Python CLI, FastAPI backend, and Next.js web UI.

It classifies each request by task type and complexity, routes to the best provider by policy, supports fallback chains, tracks cost/latency, and exposes telemetry for operations.

## Copy-Paste Quickstart (Absolute Beginner)

Run this exactly as-is in two terminals.

Terminal 1 (backend):

```bash
cd /Users/hwitzthum/router-architecture
uv sync
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY and GEMINI_API_KEY
uv run router-api
```

Terminal 2 (frontend):

```bash
cd /Users/hwitzthum/router-architecture/ui-web
npm install
npm run dev
```

Open:

- Chat UI: `http://localhost:3000`
- Mission Control Dashboard: `http://localhost:3000/dashboard`
- API docs: `http://localhost:8001/docs`

## Table of Contents

- [What This App Does](#what-this-app-does)
- [Key Features](#key-features)
- [UI Overview](#ui-overview)
- [Chat Interface](#chat-interface)
- [Mission Control Dashboard](#mission-control-dashboard)
- [How State Is Shared](#how-state-is-shared)
- [Which Button Do I Click First?](#which-button-do-i-click-first)
- [How To Start The Application](#how-to-start-the-application)
- [Typical End-to-End Workflow](#typical-end-to-end-workflow)
- [Building From Scratch — Developer Guide](#building-from-scratch--developer-guide)
- [Architecture](#architecture)
- [Provider Setup](#provider-setup)
- [Configuration](#configuration)
- [CLI Reference](#cli-reference)
- [HTTP API Reference](#http-api-reference)
- [Testing And Quality Gates](#testing-and-quality-gates)
- [Production Readiness Checklist](#production-readiness-checklist)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)

## What This App Does

Given a user prompt, the router:

1. Runs optional safety plugins.
2. Classifies task type and complexity.
3. Chooses a target model using routing rules.
4. Resolves healthy provider + fallback chain.
5. Calls the model (with retry/fallback behavior).
6. Optionally scores hallucination risk and reroutes.
7. Logs request/cost telemetry for analytics.

## Key Features

### Core routing

- Rule-based routing by `task_type` and `complexity`.
- Configurable fallback chains per rule.
- Provider health checks before selection.
- Automatic retry on transient provider unavailability.

### Multi-provider support

- Anthropic Claude Sonnet 4.6.
- Gemini 3.1 Pro Preview (`gemini-3.1-pro-preview`).
- Self-hosted OpenAI-compatible providers (e.g. vLLM/Qwen).
- Local Ollama models.

### Classification

- Regex-based classifier with categories:
  - `reasoning`, `knowledge_work`, `code`, `extraction`, `creative`, `general`
- Complexity score `0.0-1.0` from prompt heuristics.
- Optional embedding refinement against calibration corpus.

### Safety, cache, quality controls

- Optional jailbreak detection plugin.
- Optional PII redaction plugin.
- Optional hallucination scoring + reroute policy.
- Optional exact-match cache with configurable capacity.

### Telemetry and operations

- JSONL request logging to `logs/requests.jsonl`.
- Cost summary and savings vs baseline model.
- Request timeline with filters and pagination.
- Calibration runs with quality and cost metrics.

### Interfaces

- CLI (`router ...`).
- FastAPI endpoints (`/api/*`).
- Next.js UI with two main areas:
  - **Chat** (`/`) — conversational interface with per-message routing metadata
  - **Dashboard** (`/dashboard`) — Mission Control with Playground, Calibration Studio, Request Timeline

## UI Overview

The web UI has two pages linked from the top navigation bar.

### Navigation bar

A fixed top bar with:
- **Chat** link (`/`) — goes to the chat interface
- **Dashboard** link (`/dashboard`) — goes to Mission Control
- **Live** status indicator (pulsing when backend is reachable)

State is shared across both pages. Conversations and routing results persist when you switch between Chat and Dashboard.

## Chat Interface

**URL:** `http://localhost:3000`

The landing page is a hybrid chat interface. You type messages and the router picks the best model automatically.

### Layout

Three columns on desktop (sidebars collapse on mobile):

```
[Conversations 240px] | [Chat area, flex] | [Session metadata 280px, toggleable]
```

### Left sidebar — Conversation threads

- **New Chat** button — starts a fresh conversation.
- List of all past conversations (title = first user message, truncated).
- Each thread shows a message count badge.
- Click any thread to switch to it. The active thread is highlighted.
- Conversations persist across navigation and browser refresh (stored in `localStorage`).

### Center — Chat area

- Scrollable message list with user (right) and assistant (left) bubbles.
- Each assistant message shows a **"via \<model\>"** badge and a latency chip.
- Click the badge to expand inline metadata:
  - Task type, complexity, estimated cost, latency, cache hit, fallback triggered, confidence.
- Empty state when no messages are present.
- Auto-scrolls to the latest message.

### Bottom — Input area

- Auto-growing textarea.
- **Enter** to send, **Shift+Enter** for a newline.
- Loading animation while a request is in flight.
- Send button disabled during pending requests.

### Right sidebar — Session metadata

- Toggle with the chevron button.
- Shows aggregated stats for the active conversation: message count, total cost, models used, average latency.
- Provider health summary.

### Send flow

1. User types a message and presses Enter or the send button.
2. User message is appended to the active conversation.
3. Two requests fire in parallel:
   - `POST /api/route` with the full conversation history.
   - `POST /api/classify` with the prompt.
4. Assistant message with routing metadata appears.
5. Classification and route results are also shared with the Dashboard (visible in Playground panels).

## Mission Control Dashboard

**URL:** `http://localhost:3000/dashboard`

The operations and analytics surface. Panels update both from direct interaction and from Chat activity.

### Prompt Playground

- **Prompt textarea** — auto-syncs to the last prompt sent from Chat (editable).
- **Classify** — runs `/api/classify` without a model call.
- **Route Prompt** — runs full `/api/route` pipeline.
- **Classification Signal** — task type, complexity score, token estimate, risk and tool flags.
- **Routing Outcome** — response text, model used, latency, estimated cost, cache/fallback flags.
- **Provider Grid** — live health and pricing for all configured providers.
- **Cost Lens** — aggregated cost, savings, and cache metrics from logged requests.

When a chat message is sent, the Classification Signal and Routing Outcome panels automatically update with that interaction's data.

### Calibration Studio

- **Classify-only mode** — runs calibration without calling external model APIs.
- **Run Calibration** — executes the labeled calibration corpus and computes quality/cost metrics.
- **Calibration Snapshot** — run ID, timestamp, prompt count, regret rate, savings.
- **Win Rate by Task** — classification accuracy per task category.

### Request Timeline

- Filter historical requests by model, task type, cache hit, fallback triggered.
- Paginate and inspect routing decisions.
- **Page Size / Previous / Next** pagination controls.

## How State Is Shared

Chat and Dashboard share a single React context (`RouterProvider`) that lives above both routes in the app layout.

- `conversations` — full conversation list, persisted to `localStorage`.
- `lastRouteResult` — most recent routing outcome (from Chat or Dashboard Playground).
- `lastClassification` — most recent classification result (from Chat or Dashboard).
- `lastPrompt` — most recent prompt text, synced into the Dashboard textarea.

This means:
- Switching from Chat to Dashboard and back preserves all messages.
- Sending a chat message updates the Dashboard panels immediately.
- Running Classify or Route Prompt in the Dashboard updates only the Dashboard panels.
- Conversations survive page refresh.

## Which Button Do I Click First?

Use this mini walkthrough after opening `http://localhost:3000`.

**To try the chat experience:**

1. The chat interface opens automatically at `/`.
2. Type a question in the input box at the bottom.
3. Press Enter to send. The router picks a model automatically.
4. The response appears with a **"via \<model\>"** badge. Click the badge to see full routing metadata.
5. Send follow-up messages in the same thread (multi-turn context is passed to the model).
6. Click **New Chat** in the left sidebar to start a fresh conversation.
7. Click any previous thread in the sidebar to revisit it.

**To inspect routing details in the Dashboard:**

1. Click **Dashboard** in the top nav bar (or go to `/dashboard`).
2. The **Classification Signal** and **Routing Outcome** panels already show results from your last chat message.
3. You can also type a prompt directly in Playground and click **Classify** or **Route Prompt**.
4. Go to **Calibration Studio** to validate your routing policy across many prompts.
5. Go to **Request Timeline** to filter and browse historical requests.

## How To Start The Application

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- npm
- Optional for local routing/embeddings: Ollama

### 1) Install dependencies

```bash
cd /Users/hwitzthum/router-architecture
uv sync

cd /Users/hwitzthum/router-architecture/ui-web
npm install
```

### 2) Configure environment

```bash
cd /Users/hwitzthum/router-architecture
cp .env.example .env
```

Set at least:

- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

Optional runtime env vars:

- `ROUTER_CONFIG_DIR` (custom config folder)
- `ROUTER_API_HOST` (default `0.0.0.0`)
- `ROUTER_API_PORT` (default `8001`)
- `ROUTER_API_RELOAD` (`1/true/yes` to enable auto-reload)
- `ROUTER_UI_ORIGINS` (CORS list for UI origins)
- `NEXT_PUBLIC_ROUTER_API_BASE` (frontend API base, default `http://localhost:8001`)

### 3) Start backend API (terminal 1)

```bash
cd /Users/hwitzthum/router-architecture
uv run router-api
```

Backend URL: `http://localhost:8001`

### 4) Start frontend UI (terminal 2)

```bash
cd /Users/hwitzthum/router-architecture/ui-web
npm run dev
```

Frontend URL: `http://localhost:3000`

### 5) Quick health check

```bash
curl http://localhost:8001/api/health
uv run router providers list
```

### 6) Stop

Press `Ctrl+C` in both terminals.

## Typical End-to-End Workflow

### Step A: verify providers

```bash
cd /Users/hwitzthum/router-architecture
uv run router providers list
uv run router providers check gemini
uv run router providers check sonnet
uv run router providers check ollama-qwen35
```

### Step B: inspect classification before spending tokens

```bash
uv run router classify "Provide a rigorous proof that there are infinitely many primes."
```

### Step C: run routed inference

```bash
uv run router route "Summarize this architecture in 5 bullet points."
```

Output includes model used, task type, cost, latency, cache-hit, confidence.

### Step D: monitor spend and performance

```bash
uv run router cost
uv run router cost --since 2026-01-01 --until 2026-12-31
```

### Step E: run calibration to validate routing policy

Classify-only (fast, no model calls):

```bash
uv run router calibrate --no-model-calls
```

Full live calibration (uses providers):

```bash
uv run router calibrate
```

Compare against a saved baseline:

```bash
uv run router calibrate --baseline logs/calibration_<runid>.json
```

### Step F: use API directly for integration

```bash
curl -s http://localhost:8001/api/providers | jq
curl -s -X POST http://localhost:8001/api/classify \
  -H 'content-type: application/json' \
  -d '{"prompt":"Explain CAP theorem tradeoffs."}' | jq
curl -s -X POST http://localhost:8001/api/route \
  -H 'content-type: application/json' \
  -d '{"prompt":"Extract action items from this meeting note..."}' | jq
```

### Step G: operate through the web UI

1. Open `http://localhost:3000` — Chat interface.
2. Send messages, inspect routing badges, review conversation threads.
3. Open `http://localhost:3000/dashboard` — Mission Control.
4. Playground: inspect classification and routing outcomes from chat or run new prompts directly.
5. Calibration Studio: run calibration and inspect metrics.
6. Request Timeline: filter by model/task/cache/fallback and page through history.

### Step H: quality gate before shipping

```bash
# Backend
cd /Users/hwitzthum/router-architecture
uv run --with pytest --with pytest-asyncio python -m pytest -q

# Frontend
cd /Users/hwitzthum/router-architecture/ui-web
npm run test:ci
npm run build
```

## Building From Scratch — Developer Guide

This section is for developers who want to understand how the system was assembled and how to reproduce it layer by layer. Each layer depends only on the layers below it, so follow this order when building or extending the system.

```
Backend layers (Python)         Frontend layers (Next.js / TypeScript)
─────────────────────────────   ──────────────────────────────────────
1. Data models (models.py)      1. Shared types (lib/types.ts)
2. Config loading (config.py)   2. API client (lib/api.ts)
3. Provider registry            3. Shared context (lib/router-context.tsx)
4. Classifier                   4. Layout + NavBar
5. Decision engine              5. Dashboard page (/dashboard)
6. Cost tracking                6. Chat page (/)
7. Plugin chain
8. Pipeline orchestrator
9. CLI
10. FastAPI HTTP layer
```

---

### Backend

#### Layer 1 — Data models (`src/router/models.py`)

Start here. Every other module imports from this file. Define all enums and types up front so the rest of the codebase speaks the same language.

Key types to define:

- `TaskType` (enum) — the set of task categories: `reasoning`, `knowledge_work`, `code`, `extraction`, `creative`, `general`.
- `ProviderCategory` (enum) — `cloud`, `self_hosted`, `local`.
- `Provider` (Pydantic BaseModel) — one provider entry: name, base URL, API key env var, model ID, pricing per 1M tokens, context limits, enabled flag. Pydantic validators enforce non-negative prices and consistent token limits.
- `RoutingRule` (Pydantic BaseModel) — one routing rule: task type, complexity min/max, target model, fallback chain, priority.
- `ClassificationResult` (dataclass) — output of the classifier: task type, complexity score, token estimate, flags for tool use and factuality risk.
- `RoutingDecision` (dataclass) — output of the engine: selected model, fallback chain, human-readable reason string.
- `RequestRecord` (dataclass) — everything logged per request: classification, decision, model used, token counts, cost, latency, cache/fallback flags.
- `RequestResult` (dataclass) — what the API returns to callers: response text plus the key metadata a consumer cares about.
- `estimate_tokens(text)` — a utility function (word count × 1.3) used throughout.

Nothing in this file imports from the rest of the project. It is the shared vocabulary.

#### Layer 2 — Configuration loader (`src/router/config.py`)

Reads YAML files from `config/` and converts them into typed structures that the rest of the backend uses. Importing from `models.py` only.

Four YAML files drive all runtime behavior:

| File | Parsed into |
|------|-------------|
| `config/providers.yaml` | `list[Provider]` |
| `config/routing.yaml` | `list[RoutingRule]` sorted by priority |
| `config/plugins.yaml` | `PluginConfig` (cache, safety, hallucination, embedding sub-configs) |
| `config/calibration_prompts.yaml` | list of labeled prompts for calibration runs |

`load_config(config_dir?)` is the single entry point. It reads all four files, validates them against the Pydantic/dataclass definitions from Layer 1, and returns a `RouterConfig` object.

The config dir defaults to `config/` at the repo root. Override with `ROUTER_CONFIG_DIR` or by passing a path explicitly (used in tests).

#### Layer 3 — Provider registry (`src/router/providers.py`)

The registry is a module-level `dict[str, Provider]` protected by a `threading.RLock`. It is populated at startup from the parsed config (Layer 2) and accessed throughout the request lifecycle.

Key responsibilities:

- `load_providers_from_config(providers)` — clears the registry and reloads from a config list.
- `call_model(name, messages)` — selects the right calling strategy based on provider category:
  - **Anthropic** (`claude-*` model IDs): uses `urllib` with the Anthropic Messages API format and `anthropic-version` header.
  - **All others**: uses the OpenAI Python SDK with `base_url` override pointed at the provider's endpoint (Gemini, vLLM, Ollama all expose OpenAI-compatible `/chat/completions`).
- `check_provider_health(name)` — lightweight HEAD/GET to the provider's base URL with a short timeout; returns bool.
- `start_health_monitor(providers)` — starts a background thread that periodically runs health checks on all registered providers and updates an in-memory health cache.

This layer defines four exceptions that the pipeline layer uses for control flow: `ProviderUnavailableError`, `ModelCallError`, `UnknownProviderError`, `AllProvidersUnavailableError`.

#### Layer 4 — Classifier (`src/router/classifier.py`)

Takes a list of chat messages and returns a `ClassificationResult`. Imports from `models.py` only.

Two-phase classification:

1. **Keyword matching** — regex patterns are defined for each `TaskType`. The classifier runs all pattern sets against the concatenated user/system message text and picks the type with the most hits. If no type scores at least one hit, it falls back to `general`.

2. **Embedding refinement** (optional) — if the embedding plugin is enabled and a corpus is initialized, the classifier requests an embedding vector for the prompt and runs a k-nearest-neighbor vote against the labeled calibration corpus. If the k-NN vote clears a confidence threshold, it overrides the keyword result.

After task type is determined, `_complexity_score()` computes a `0.0–1.0` score from:
- Prompt token count (longer = harder)
- Presence of multi-step language ("first", "then", "finally", etc.)
- Number of question marks (multi-faceted requests)
- Domain jargon density (eigenvalue, microservice, latency, etc.)
- A base offset per task type (`reasoning` starts at 0.5, `general` at 0.2)

The classifier is stateless and has no I/O side effects, making it easy to unit test in isolation.

#### Layer 5 — Decision engine (`src/router/engine.py`)

Takes a `ClassificationResult` and the list of `RoutingRule`s from config, and returns a `RoutingDecision`. Imports from `models.py` only.

Two functions:

- `route_request(classification, rules, default_model)` — iterates rules in priority order, finds the first where `task_type` matches and `complexity` falls within `[complexity_min, complexity_max]`, and returns that rule's target model and fallback chain. If nothing matches, returns the configured `default_model` with an empty fallback chain.

- `resolve_available_model(decision, health_check_fn)` — walks `[selected_model] + fallback_chain` and returns the first model that passes a health check. Raises `AllProvidersUnavailableError` if every candidate is unhealthy.

The engine is also purely functional — no I/O, no side effects, easy to test with synthetic rules and health functions.

#### Layer 6 — Cost tracking (`src/router/cost.py`)

Handles two concerns:

- **Per-request cost** — `compute_cost(input_tokens, output_tokens, input_price, output_price, cached_input_price)` returns a USD float using the per-million-token pricing from the provider config.

- **JSONL logging** — `log_request(record)` appends a JSON line to `logs/requests.jsonl`. Each line contains: id, timestamp, model used, task type, token counts, cost, latency, cache/fallback flags, confidence score.

- **Reporting** — `get_cost_summary(since, until)` and `get_request_timeline(filters)` read and aggregate the JSONL log; these power the Dashboard's Cost Lens and Request Timeline panels.

#### Layer 7 — Plugin chain (`src/router/plugins/`)

Optional middleware that runs before classification. Each plugin receives the message list and returns a result with an `outcome` flag:

- `PASS` — no action, continue with original messages.
- `SANITIZE` — continue with a cleaned version of messages (used by PII redaction).
- `BLOCK` — reject the request before any model call.

Plugins shipped:

| Plugin | File | What it does |
|--------|------|--------------|
| Jailbreak detection | `plugins/jailbreak.py` | Pattern-matches known jailbreak phrases; blocks on match |
| PII redaction | `plugins/pii.py` | Replaces phone numbers, email addresses, SSNs with placeholders |
| Hallucination scoring | `plugins/hallucination.py` | Scores response text for hedging language; used post-generation to optionally reroute |

`build_plugin_chain(safety_config)` constructs the enabled plugin list from config. `run_plugin_chain(chain, messages)` runs them in sequence, stopping early on BLOCK.

The cache module (`cache.py`) also lives at this layer: an in-memory LRU dict keyed on a hash of the message list. `lookup(messages)` returns a cached response or `None`; `store(messages, response)` adds an entry.

#### Layer 8 — Pipeline orchestrator (`src/router/pipeline.py`)

This is the central module that wires all previous layers together into a single `handle_request(messages, config?)` call. The execution order mirrors the pipeline diagram in the Architecture section:

```
safety plugins → cache lookup → classify → route → health resolve
  → call model (with retry/fallback) → hallucination score → cache store
  → cost compute → log → return RequestResult
```

`pipeline.py` also owns singleton config initialization. `get_config()` uses double-checked locking to load config exactly once (or when `reload_config()` is called explicitly). On first load it also calls `load_providers_from_config()` and `start_health_monitor()`, so the pipeline self-bootstraps.

#### Layer 9 — CLI (`src/router/cli.py`)

A [Typer](https://typer.tiangolo.com/) CLI that exposes all pipeline operations as subcommands:

| Command | What it calls |
|---------|---------------|
| `router providers list` | `list_providers()` from registry |
| `router providers check <name>` | `check_provider_health()` |
| `router classify <prompt>` | `classify_request()` directly |
| `router route <prompt>` | `handle_request()` full pipeline |
| `router cost` | `get_cost_summary()` |
| `router calibrate` | `run_calibration()` |

The entry point is registered in `pyproject.toml` under `[project.scripts]` as `router-cli` (invoked as `uv run router ...`).

#### Layer 10 — FastAPI HTTP layer (`src/router/api.py`)

Wraps the pipeline and reporting functions in HTTP endpoints using FastAPI. The app is created by `create_app()` and mounted by the `router-api` entry point in `pyproject.toml`.

Input envelope: `PromptEnvelope` accepts either a `prompt` string (converted to a single user message) or a `messages` list (passed through as-is). This is how multi-turn chat context flows from the UI to the pipeline.

CORS is configured via `ROUTER_UI_ORIGINS` (defaults to `localhost:3000`). The allowed methods include `OPTIONS` for browser preflight requests.

---

### Frontend

The UI is a Next.js App Router application in `ui-web/`. Build the layers in this order.

#### Layer 1 — Shared TypeScript types (`ui-web/lib/types.ts`)

Mirror the backend's API response shapes as TypeScript interfaces. Nothing else in the frontend should define these inline.

Key types:

- `ClassificationResult`, `RouteResult` — match the API JSON shapes.
- `ProviderStatus`, `CostSummary`, `RequestEntry` — for the Dashboard panels.
- `Message` — one chat turn: `id`, `role`, `content`, `timestamp`, plus optional routing metadata fields (`model_used`, `task_type`, `estimated_cost`, `latency_ms`, `cache_hit`, `fallback_triggered`, `confidence`).
- `Conversation` — a thread: `id`, `title`, `messages[]`, `created_at`.

#### Layer 2 — Shared API client (`ui-web/lib/api.ts`)

Generic typed wrappers around `fetch` so individual components don't construct requests by hand.

```typescript
const API_BASE = process.env.NEXT_PUBLIC_ROUTER_API_BASE ?? "http://localhost:8001";
apiGet<T>(path: string): Promise<T>
apiPost<T>(path: string, body: unknown): Promise<T>
```

Both functions throw on non-2xx responses with the backend error message surfaced.

#### Layer 3 — Shared context (`ui-web/lib/router-context.tsx`)

The most architecturally important frontend file. Creates a `RouterProvider` React context that lives above both pages in the layout. Without this, state is lost every time the user navigates between Chat and Dashboard.

State it holds:

```typescript
conversations: Conversation[]          // all threads, persisted to localStorage
activeId: string                       // which thread is selected
lastRouteResult: RouteResult | null    // last routing outcome (from either page)
lastClassification: ClassificationResult | null
lastPrompt: string                     // synced to Dashboard textarea
```

Key behaviors:
- On mount, reads `conversations` from `localStorage` to restore state across refreshes and navigations.
- `sendMessage(prompt)` fires `POST /api/route` and `POST /api/classify` in parallel, appends the assistant message, and updates `lastRouteResult`, `lastClassification`, and `lastPrompt`.
- Every conversation change writes back to `localStorage`.

#### Layer 4 — Layout and navigation (`ui-web/app/layout.tsx`, `ui-web/app/nav-bar.tsx`)

`layout.tsx` is a server component (Next.js default). It sets up fonts, global metadata, and wraps children with `RouterProvider`. Because `RouterProvider` is a client component, it is imported with `"use client"`.

`nav-bar.tsx` is a separate client component (it needs `usePathname` for active-link highlighting). It renders the fixed top bar with Chat and Dashboard links and the Live status indicator.

Keep `layout.tsx` as a server component and isolate all client-side interactivity into `nav-bar.tsx` and the page components.

#### Layer 5 — Dashboard page (`ui-web/app/dashboard/page.tsx`)

A client component (`"use client"`) that consumes the shared context via `useRouter()`. It has its own local state for the Playground (prompt text, classification result, route result, calibration result, timeline entries) that overrides the context values when the user runs actions directly from the Dashboard.

Panel layout (rendered as a grid of cards):
1. Prompt Playground — textarea, Classify button, Route button
2. Classification Signal — reads local state, falls back to `lastClassification` from context
3. Routing Outcome — reads local state, falls back to `lastRouteResult` from context
4. Provider Grid — polls `GET /api/providers` on mount
5. Cost Lens — polls `GET /api/cost` on mount
6. Calibration Studio — calls `POST /api/calibrate`
7. Request Timeline — calls `GET /api/requests` with filter state

#### Layer 6 — Chat page (`ui-web/app/page.tsx`)

A client component that consumes the shared context and renders the three-column layout.

Important: initialize `conversations` state with an empty array and populate from `localStorage` only inside `useEffect`. This avoids a React hydration mismatch — the server renders an empty list and the client hydrates it from storage after mount. Using `useState(loadFromLocalStorage)` directly causes the server-rendered HTML to differ from the initial client render (because `localStorage` is not available during SSR).

Conversation list (left sidebar) and message list (center) are derived from the context's `conversations` array. The send handler calls `context.sendMessage(prompt)` which handles the API calls and state updates.

---

### Testing as you go

After each backend layer, add unit tests in `tests/unit/` before moving to the next:

```bash
uv run --with pytest --with pytest-asyncio python -m pytest tests/unit/ -q
```

After each frontend layer, run:

```bash
cd ui-web && npm run test:ci
```

The integration tests in `tests/integration/` test the full pipeline end to end (including the FastAPI layer) and should pass after Layer 10 is complete.

## Architecture

Pipeline order:

1. Ingress and optional safety plugins.
2. Cache lookup.
3. Task classification.
4. Rule-based decision engine.
5. Provider resolution by health + fallback chain.
6. Model invocation.
7. Optional hallucination confidence check/reroute.
8. Logging and cost accounting.

Key implementation files:

- `src/router/pipeline.py`
- `src/router/classifier.py`
- `src/router/engine.py`
- `src/router/providers.py`
- `src/router/cost.py`
- `src/router/plugins/*`

## Provider Setup

Default providers from `config/providers.yaml`:

| Provider key | Display name | Category | Model ID | Input/M | Output/M | Cached Input/M |
|---|---|---|---|---:|---:|---:|
| `sonnet` | Claude Sonnet 4.6 | cloud | `claude-sonnet-4-6` | $3.00 | $15.00 | $0.300 |
| `gemini` | Gemini 3.1 Pro | cloud | `gemini-3.1-pro-preview` | $2.00 | $12.00 | $0.200 |
| `qwen` | Qwen 3.5 (self-hosted) | self_hosted | `Qwen/Qwen3.5` | $0.60 | $3.60 | $0.000 |
| `ollama-qwen35` | Qwen 3.5 (Ollama local) | local | `qwen3.5:cloud` | $0.550 | $3.50 | $0.550 |

Notes:

- Anthropic provider is called through Anthropic's native Messages API path with required headers.
- Gemini/self-hosted/Ollama are called through OpenAI-compatible chat completion endpoints.
- Inference-time fallback can occur even when a provider is marked healthy (e.g. quota/rate-limit during generation).

## Configuration

All policy is config-driven in `config/`:

- `providers.yaml`: model endpoints, keys, pricing, enable flags.
- `routing.yaml`: routing rules and fallback chains.
- `plugins.yaml`: safety/cache/hallucination/embedding toggles.
- `calibration_prompts.yaml`: labeled calibration corpus.

### Example: routing rule

```yaml
- task_type: "reasoning"
  complexity_min: 0.6
  complexity_max: 1.0
  target_model: "gemini"
  fallback_chain: ["sonnet", "ollama-qwen35"]
  priority: 1
```

### Example: API endpoint selection in UI

Frontend defaults to `http://localhost:8001` unless `NEXT_PUBLIC_ROUTER_API_BASE` is set.

## CLI Reference

```bash
# Providers
router providers list
router providers check sonnet

# Classify (no model call)
router classify "Prove this statement step-by-step"

# Route (live model call)
router route "Summarize this design doc"

# Cost reports
router cost
router cost --since 2026-01-01 --until 2026-12-31

# Calibration
router calibrate --no-model-calls
router calibrate
router calibrate --baseline logs/calibration_<runid>.json

# Custom config directory
router --config-dir /path/to/config providers list
```

## HTTP API Reference

Base URL (default): `http://localhost:8001`

- `GET /api/health`
  - router status and configured provider count
- `POST /api/classify`
  - classify prompt/messages without model generation
- `POST /api/route`
  - full routed inference; accepts `{ prompt, messages }` for multi-turn context
- `GET /api/providers`
  - provider metadata + live health
- `GET /api/cost`
  - cost summary (`since`, `until` optional ISO timestamps)
- `POST /api/calibrate`
  - calibration run (`no_model_calls` boolean)
- `GET /api/requests`
  - request timeline with filters:
    - `since`, `until`
    - `model`, `task_type`
    - `cache_hit`, `fallback_triggered`
    - `limit`, `offset`

OpenAPI docs are available when backend is running:

- `http://localhost:8001/docs`
- `http://localhost:8001/redoc`

## Testing And Quality Gates

### Backend

```bash
cd /Users/hwitzthum/router-architecture
uv run --with pytest --with pytest-asyncio python -m pytest -q
```

Current baseline: `334 passed, 1 skipped`.

The skipped test is the optional live calibration test unless enabled explicitly:

```bash
ROUTER_RUN_LIVE_CALIBRATION=1 uv run --with pytest --with pytest-asyncio python -m pytest tests/calibration/test_calibration.py -q
```

### Frontend

```bash
cd /Users/hwitzthum/router-architecture/ui-web
npm run test:ci
```

`test:ci` enforces:

1. lint with zero warnings
2. Vitest coverage thresholds

## Production Readiness Checklist

Use this checklist before moving to production.

1. Security plugins:
  - Enable `safety.jailbreak_detection.enabled: true`.
  - Enable `safety.pii_redaction.enabled: true`.
  - Keep these enabled by default in production config.
2. Hallucination policy:
  - For high-risk use cases, enable `hallucination.enabled: true`.
  - Set `reroute_on_low_confidence: true` and a safe `reroute_target` (usually `sonnet`).
3. Cache policy:
  - Only enable cache if your deployment is single-tenant or cache keys are tenant-isolated.
  - If in doubt, keep `cache.enabled: false` in production.
4. Provider validation:
  - Run `uv run router providers list` and `uv run router providers check <provider>` for all enabled providers.
  - Confirm model IDs, quotas, and billing are active (healthy endpoints can still fail at generation time due to quota).
5. Pricing validation:
  - Verify `config/providers.yaml` values for `input_price`, `output_price`, and `cached_input_price`.
  - Confirm current critical values:
    - Sonnet: `3.00 / 15.00 / 0.300` per 1M tokens (input/output/cached input)
    - Gemini: `2.00 / 12.00 / 0.200` per 1M tokens
    - Ollama qwen3.5:cloud: `0.550 / 3.50 / 0.550` per 1M tokens
6. Secrets and environment:
  - Store API keys in a secret manager or protected environment variables.
  - Do not bake keys into images or source code.
  - Restrict CORS via `ROUTER_UI_ORIGINS` to real frontend origins only.
7. API hardening (recommended before internet exposure):
  - Put API behind authentication/authorization (gateway, reverse proxy, or middleware).
  - Add rate limiting and request-size limits at the edge.
8. Observability:
  - Ensure `logs/requests.jsonl` is persisted, rotated, and monitored.
  - Add alerting on provider failures, high fallback rates, and error spikes.
9. Quality gate:
  - Backend: `uv run --with pytest --with pytest-asyncio python -m pytest -q`
  - Frontend: `cd ui-web && npm run test:ci && npm run build`
10. Release smoke test:
  - Run one real `router route` request for each critical task type (`reasoning`, `code`, `extraction`, `knowledge_work`).
  - Verify `model_used`, `fallback_triggered`, latency, and estimated cost are within expected ranges.

## Troubleshooting

### `router route` uses fallback unexpectedly

Check provider and live generation separately:

```bash
uv run router providers list
```

A provider may show healthy but still fail inference due to quota/rate-limit/model access. In that case routing falls back by design.

### Gemini model ID mismatch

Use `gemini-3.1-pro-preview` for Gemini 3.1 Pro in this project config.

### Ollama provider unhealthy

Ensure Ollama is running and the configured model is loaded:

```bash
ollama list
```

Configured local provider model: `qwen3.5:cloud`.

### UI cannot reach backend

Set frontend API base:

```bash
export NEXT_PUBLIC_ROUTER_API_BASE=http://localhost:8001
```

### Chat conversations not persisting

Conversations are stored in browser `localStorage`. Clearing site data will remove them. They are not synced to the backend.

### Dashboard panels not updating from Chat

Both pages share a React context (`RouterProvider`). If panels are stale, try navigating back to Chat and sending a new message — this refreshes `lastRouteResult` and `lastClassification` in the shared context.

## Project Structure

```text
router-architecture/
├── config/
│   ├── providers.yaml
│   ├── routing.yaml
│   ├── plugins.yaml
│   └── calibration_prompts.yaml
├── src/router/
│   ├── api.py              # FastAPI app (includes CORS with OPTIONS support)
│   ├── cli.py
│   ├── pipeline.py
│   ├── classifier.py
│   ├── engine.py
│   ├── providers.py
│   ├── cost.py
│   ├── calibration.py
│   └── plugins/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── calibration/
├── ui-web/
│   ├── app/
│   │   ├── layout.tsx          # Root layout with RouterProvider + NavBar
│   │   ├── nav-bar.tsx         # Top nav (Chat / Dashboard links, Live indicator)
│   │   ├── page.tsx            # Chat interface (/)
│   │   ├── dashboard/
│   │   │   └── page.tsx        # Mission Control dashboard (/dashboard)
│   │   └── globals.css         # Design system + chat + nav styles
│   └── lib/
│       ├── types.ts            # Shared TypeScript types
│       ├── api.ts              # Shared API client (apiGet, apiPost)
│       ├── router-context.tsx  # RouterProvider: shared conversations + routing state
│       ├── format.ts
│       ├── timeline-query.ts
│       └── *.test.ts
├── logs/
├── .env.example
├── pyproject.toml
└── uv.lock
```
