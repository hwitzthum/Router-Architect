# Quickstart: AI Model Router

## Prerequisites

- Python 3.11+
- At least one model provider configured:
  - **Ollama** (easiest): Install from https://ollama.com, then `ollama pull llama3`
  - **Cloud APIs**: Obtain API keys for Anthropic and/or Google
  - **Self-hosted Qwen**: vLLM or SGLang running Qwen 3.5 (optional)

## Install

```bash
cd router-architecture
uv sync          # installs all dependencies and the router CLI
```

> If you don't have `uv`, install it: `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Configure Providers

Edit `config/providers.yaml` to enable the providers you have available. At minimum, enable one provider.

Set API keys as environment variables:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="AI..."
```

For Ollama, ensure the service is running:

```bash
ollama serve  # Start Ollama (if not already running)
```

## Verify Setup

```bash
# Check which providers are healthy
router providers list

# Expected output:
# sonnet      ✓ healthy   (cloud)
# gemini      ✓ healthy   (cloud)
# qwen        ✗ offline   (self_hosted)
# ollama-qwen35  ✓ healthy   (local)
```

## Route Your First Request

```bash
router route "Summarize the key points of this paragraph: ..."
```

Expected output:

```
Response: [Model's summary here]

--- Metadata ---
Model used:    ollama-qwen35
Task type:     extraction
Cost:          $0.000000
Latency:       1250ms
Cache hit:     no
```

## Try Different Task Types

```bash
# Reasoning → should route to Gemini
router route "Solve this logic puzzle: ..."

# Knowledge work → should route to Sonnet
router route "Evaluate the business strategy of ..."

# Code → depends on complexity
router route "Write a Python function that ..."

# Extraction → should route to Ollama/Qwen (cheapest)
router route "Translate this to French: ..."
```

## View Cost Report

```bash
router cost
```

## Run Calibration

```bash
router calibrate
```

This runs 20+ prompts against all enabled models and reports win rate, latency, cost, and regret rate.

## What's Next

1. Tune routing rules in `config/routing.yaml` based on calibration results
2. Add more providers (additional Ollama models, different cloud models)
3. Enable plugins in `config/plugins.yaml` (caching, safety filters)