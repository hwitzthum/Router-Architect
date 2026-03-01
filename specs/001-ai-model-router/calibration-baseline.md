# Calibration Baseline — AI Model Router

**Run ID**: ecbd5192
**Date**: 2026-02-28
**Mode**: Classify-only (no API calls — heuristic routing only)
**Prompts tested**: 20

---

## Summary Metrics

| Metric | Value |
|--------|-------|
| Prompts tested | 20 |
| Models in pool | gemini, ollama-qwen35, qwen, sonnet |
| Regret rate | **5.0%** (lower is better) |
| Cost savings vs all-Sonnet baseline | **56.4%** |

---

## Classification Accuracy by Task Type

| Task Type | Accuracy | Notes |
|-----------|----------|-------|
| code | 100% | All 4 code prompts correctly classified |
| creative | 100% | All creative prompts correctly classified |
| extraction | 100% | All extraction prompts correctly classified |
| general | 100% | General category correctly classified |
| **knowledge_work** | **75%** | 1 of 4 knowledge prompts misclassified |
| reasoning | 100% | All reasoning prompts correctly classified |

**Overall classification accuracy**: 95% (19/20 correct)

The one misclassification is a knowledge-work prompt that scored above the knowledge→reasoning boundary — a borderline "evaluation" prompt with high complexity signals.

---

## Routing Distribution

| Model | Requests | Avg Cost/Request |
|-------|----------|-----------------|
| gemini | 5 | $0.0000156 |
| ollama-qwen35 | 6 | $0.000000 |
| qwen | 4 | $0.0000130 |
| sonnet | 5 | $0.0000960 |

**Zero-cost (Ollama) share**: 30% of requests → direct cost elimination

---

## Cost Analysis

| Model | Total Cost |
|-------|-----------|
| sonnet | $0.000480 |
| gemini | $0.000078 |
| qwen | $0.000052 |
| ollama-qwen35 | $0.000000 |
| **Total** | **$0.000610** |

vs. all-Sonnet baseline: $0.001400
→ **56.4% cost reduction** (article target: 46%)

---

## Latency (Classify-Only Mode)

All latencies are near-zero in classify-only mode since no actual model calls are made. Realworld latencies would be:
- sonnet: ~800–1500ms (cloud API)
- gemini: ~600–1200ms (cloud API)
- qwen: ~200–500ms (self-hosted vLLM, low network latency)
- ollama-qwen35: ~500–2000ms (local, hardware-dependent)

---

## Known Issues

1. **knowledge_work 75% accuracy**: The "Evaluate the strengths and weaknesses of this business strategy" style prompt can be misclassified as reasoning due to `evaluate` overlap. Workaround: add `business`, `strategy`, `stakeholder` to knowledge keyword list (done in T039).

2. **Regret rate 5%**: One prompt (the misclassified knowledge_work one) would have been better served by Sonnet than the routed model. This is acceptable for V1.

---

## Improvement Targets

| Target | Current | Goal |
|--------|---------|------|
| knowledge_work accuracy | 75% | ≥ 85% |
| Overall accuracy | 95% | ≥ 95% ✓ |
| Regret rate | 5% | < 10% ✓ |
| Cost savings | 56.4% | > 40% ✓ |

---

## How to Re-run

```bash
# Classify-only (no API keys needed, ~1s)
router calibrate --no-model-calls

# Full routing (requires API keys, ~60s)
router calibrate

# Compare against this baseline
router calibrate --baseline logs/calibration_ecbd5192.json
```