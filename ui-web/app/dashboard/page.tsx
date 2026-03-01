"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { toLocalTimestamp, toUsd } from "../../lib/format";
import { buildTimelineQuery } from "../../lib/timeline-query";
import { apiGet, apiPost } from "../../lib/api";
import { useRouter } from "../../lib/router-context";
import type {
  ClassificationResult,
  RouteResult,
  ProviderPayload,
  CostSummary,
  CalibrationResult,
  TimelinePayload,
} from "../../lib/types";

type SectionKey = "playground" | "calibration" | "timeline";

export default function DashboardPage() {
  // Shared context — latest results from chat
  const {
    lastClassification,
    lastRouteResult,
    lastPrompt,
  } = useRouter();

  const [activeSection, setActiveSection] = useState<SectionKey>("playground");
  const [prompt, setPrompt] = useState(
    "Prove step by step that there are infinitely many prime numbers."
  );
  // Local overrides: if user runs classify/route from dashboard, use local result.
  // Otherwise fall back to shared context from chat.
  const [localClassifyResult, setLocalClassifyResult] = useState<ClassificationResult | null>(null);
  const [localRouteResult, setLocalRouteResult] = useState<RouteResult | null>(null);
  const [providerPayload, setProviderPayload] = useState<ProviderPayload | null>(null);
  const [costSummary, setCostSummary] = useState<CostSummary | null>(null);
  const [loadingClassify, setLoadingClassify] = useState(false);
  const [loadingRoute, setLoadingRoute] = useState(false);
  const [loadingPanels, setLoadingPanels] = useState(true);

  const [calibrationResult, setCalibrationResult] = useState<CalibrationResult | null>(null);
  const [noModelCalls, setNoModelCalls] = useState(true);
  const [calibrating, setCalibrating] = useState(false);

  const [timeline, setTimeline] = useState<TimelinePayload>({ total: 0, items: [] });
  const [loadingTimeline, setLoadingTimeline] = useState(false);
  const [timelineModel, setTimelineModel] = useState("all");
  const [timelineTaskType, setTimelineTaskType] = useState("all");
  const [timelineCacheHit, setTimelineCacheHit] = useState("all");
  const [timelineFallback, setTimelineFallback] = useState("all");
  const [timelineLimit, setTimelineLimit] = useState(25);
  const [timelineOffset, setTimelineOffset] = useState(0);

  const [error, setError] = useState<string | null>(null);

  // Merge: local dashboard result takes priority, otherwise show chat result
  const classifyResult = localClassifyResult ?? lastClassification;
  const routeResult = localRouteResult ?? lastRouteResult;

  // Sync prompt field when chat sends a new prompt
  useEffect(() => {
    if (lastPrompt) {
      setPrompt(lastPrompt);
    }
  }, [lastPrompt]);

  const healthyCount = useMemo(() => {
    if (!providerPayload) return 0;
    return providerPayload.providers.filter((p) => p.enabled && p.healthy).length;
  }, [providerPayload]);

  const providersForFilter = useMemo(() => {
    const names = new Set((providerPayload?.providers ?? []).map((p) => p.name));
    names.add("cache");
    return Array.from(names).sort();
  }, [providerPayload]);

  async function refreshPanels() {
    setLoadingPanels(true);
    setError(null);
    try {
      const [providers, cost] = await Promise.all([
        apiGet<ProviderPayload>("/api/providers"),
        apiGet<CostSummary>("/api/cost")
      ]);
      setProviderPayload(providers);
      setCostSummary(cost);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard panels.");
    } finally {
      setLoadingPanels(false);
    }
  }

  async function refreshTimeline(offset = timelineOffset, limit = timelineLimit) {
    setLoadingTimeline(true);
    setError(null);
    try {
      const query = buildTimelineQuery({
        offset,
        limit,
        model: timelineModel,
        taskType: timelineTaskType,
        cacheHit: timelineCacheHit,
        fallbackTriggered: timelineFallback
      });
      const payload = await apiGet<TimelinePayload>(`/api/requests?${query}`);
      setTimeline(payload);
      setTimelineOffset(offset);
      setTimelineLimit(limit);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load request timeline.");
    } finally {
      setLoadingTimeline(false);
    }
  }

  useEffect(() => {
    void (async () => {
      await Promise.all([refreshPanels(), refreshTimeline(0, timelineLimit)]);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleClassify(event: FormEvent) {
    event.preventDefault();
    setLoadingClassify(true);
    setError(null);
    try {
      const payload = await apiPost<ClassificationResult>("/api/classify", { prompt });
      setLocalClassifyResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Classification failed.");
    } finally {
      setLoadingClassify(false);
    }
  }

  async function handleRoute() {
    setLoadingRoute(true);
    setError(null);
    try {
      const payload = await apiPost<RouteResult>("/api/route", { prompt });
      setLocalRouteResult(payload);
      await Promise.all([refreshPanels(), refreshTimeline(timelineOffset, timelineLimit)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Routing failed.");
    } finally {
      setLoadingRoute(false);
    }
  }

  async function handleCalibrate() {
    setCalibrating(true);
    setError(null);
    try {
      const payload = await apiPost<CalibrationResult>("/api/calibrate", {
        no_model_calls: noModelCalls
      });
      setCalibrationResult(payload);
      await refreshPanels();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Calibration failed.");
    } finally {
      setCalibrating(false);
    }
  }

  async function submitTimelineFilters(event: FormEvent) {
    event.preventDefault();
    await refreshTimeline(0, timelineLimit);
  }

  return (
    <main className="shell">
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />
      <header className="hero">
        <p className="kicker">Router-Architecture</p>
        <h1>Mission Control</h1>
        <p className="subtitle">
          Real-time model routing operations with live provider status, prompt lab, calibration,
          and request timeline telemetry in one cockpit.
        </p>
        <div className="hero-metrics">
          <div>
            <span>Healthy Providers</span>
            <strong>{providerPayload ? healthyCount : "..."}</strong>
          </div>
          <div>
            <span>Configured Providers</span>
            <strong>{providerPayload ? providerPayload.providers.length : "..."}</strong>
          </div>
          <div>
            <span>Requests Logged</span>
            <strong>{costSummary ? costSummary.request_count : "..."}</strong>
          </div>
        </div>
      </header>

      <nav className="section-switch" aria-label="Mission sections">
        <button
          type="button"
          className={activeSection === "playground" ? "tab active" : "tab"}
          onClick={() => setActiveSection("playground")}
        >
          Playground
        </button>
        <button
          type="button"
          className={activeSection === "calibration" ? "tab active" : "tab"}
          onClick={() => setActiveSection("calibration")}
        >
          Calibration Studio
        </button>
        <button
          type="button"
          className={activeSection === "timeline" ? "tab active" : "tab"}
          onClick={() => setActiveSection("timeline")}
        >
          Request Timeline
        </button>
      </nav>

      {error ? <p className="error-banner">{error}</p> : null}

      {activeSection === "playground" ? (
        <section className="grid">
          <article className="panel panel-playground">
            <div className="panel-header">
              <h2>Prompt Playground</h2>
              <span>Classify and route through live API</span>
            </div>
            <form onSubmit={handleClassify}>
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="Enter a user request for the router..."
                rows={7}
              />
              <div className="actions">
                <button type="submit" disabled={loadingClassify || !prompt.trim()}>
                  {loadingClassify ? "Classifying..." : "Classify"}
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={loadingRoute || !prompt.trim()}
                  onClick={handleRoute}
                >
                  {loadingRoute ? "Routing..." : "Route Prompt"}
                </button>
              </div>
            </form>
          </article>

          <article className="panel">
            <div className="panel-header">
              <h2>Classification Signal</h2>
              <span>Task and complexity inference</span>
            </div>
            {classifyResult ? (
              <dl className="key-value">
                <div>
                  <dt>Task Type</dt>
                  <dd>{classifyResult.task_type}</dd>
                </div>
                <div>
                  <dt>Complexity</dt>
                  <dd>{classifyResult.complexity.toFixed(2)}</dd>
                </div>
                <div>
                  <dt>Token Estimate</dt>
                  <dd>{classifyResult.token_estimate}</dd>
                </div>
                <div>
                  <dt>Requires Tools</dt>
                  <dd>{classifyResult.requires_tools ? "Yes" : "No"}</dd>
                </div>
                <div>
                  <dt>Factuality Risk</dt>
                  <dd>{classifyResult.factuality_risk ? "Yes" : "No"}</dd>
                </div>
              </dl>
            ) : (
              <p className="empty">Run classify to inspect the router&apos;s feature extraction.</p>
            )}
          </article>

          <article className="panel panel-response">
            <div className="panel-header">
              <h2>Routing Outcome</h2>
              <span>Provider selection and model response</span>
            </div>
            {routeResult ? (
              <>
                <dl className="key-value compact">
                  <div>
                    <dt>Model Used</dt>
                    <dd>{routeResult.model_used}</dd>
                  </div>
                  <div>
                    <dt>Task Type</dt>
                    <dd>{routeResult.task_type}</dd>
                  </div>
                  <div>
                    <dt>Latency</dt>
                    <dd>{routeResult.latency_ms} ms</dd>
                  </div>
                  <div>
                    <dt>Estimated Cost</dt>
                    <dd>{toUsd(routeResult.estimated_cost)}</dd>
                  </div>
                  <div>
                    <dt>Cache Hit</dt>
                    <dd>{routeResult.cache_hit ? "Yes" : "No"}</dd>
                  </div>
                  <div>
                    <dt>Fallback Triggered</dt>
                    <dd>{routeResult.fallback_triggered ? "Yes" : "No"}</dd>
                  </div>
                </dl>
                <pre className="response-box">{routeResult.response}</pre>
              </>
            ) : (
              <p className="empty">Run route to execute the full pipeline.</p>
            )}
          </article>

          <article className="panel">
            <div className="panel-header">
              <h2>Provider Grid</h2>
              <span>Health and pricing posture</span>
            </div>
            {loadingPanels ? (
              <p className="empty">Loading providers...</p>
            ) : providerPayload ? (
              <div className="provider-list">
                {providerPayload.providers.map((provider) => (
                  <div key={provider.name} className="provider-card">
                    <div className="provider-title">
                      <strong>{provider.display_name}</strong>
                      <span
                        className={`status-dot ${
                          provider.enabled && provider.healthy ? "ok" : "down"
                        }`}
                      />
                    </div>
                    <p>
                      {provider.name} • {provider.category}
                    </p>
                    <p className="mono">{provider.model_id}</p>
                    <p>
                      In: ${provider.input_price}/M • Out: ${provider.output_price}/M • Cached In: $
                      {provider.cached_input_price}/M
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty">Provider telemetry unavailable.</p>
            )}
          </article>

          <article className="panel">
            <div className="panel-header">
              <h2>Cost Lens</h2>
              <span>Economics and cache effects</span>
            </div>
            {loadingPanels ? (
              <p className="empty">Loading cost summary...</p>
            ) : costSummary ? (
              <dl className="key-value">
                <div>
                  <dt>Total Cost</dt>
                  <dd>{toUsd(costSummary.total_cost)}</dd>
                </div>
                <div>
                  <dt>Baseline Cost</dt>
                  <dd>{toUsd(costSummary.baseline_cost)}</dd>
                </div>
                <div>
                  <dt>Savings</dt>
                  <dd>{costSummary.savings_percentage.toFixed(2)}%</dd>
                </div>
                <div>
                  <dt>Cache Hit Rate</dt>
                  <dd>{(costSummary.cache_hit_rate * 100).toFixed(2)}%</dd>
                </div>
              </dl>
            ) : (
              <p className="empty">Cost telemetry unavailable.</p>
            )}
          </article>
        </section>
      ) : null}

      {activeSection === "calibration" ? (
        <section className="grid">
          <article className="panel panel-playground">
            <div className="panel-header">
              <h2>Calibration Studio</h2>
              <span>Run evaluation sweeps and inspect quality economics</span>
            </div>
            <div className="calibration-controls">
              <label className="checkbox-line">
                <input
                  type="checkbox"
                  checked={noModelCalls}
                  onChange={(event) => setNoModelCalls(event.target.checked)}
                />
                <span>Classify-only mode (no provider model calls)</span>
              </label>
              <button type="button" disabled={calibrating} onClick={handleCalibrate}>
                {calibrating ? "Running Calibration..." : "Run Calibration"}
              </button>
            </div>
          </article>

          <article className="panel">
            <div className="panel-header">
              <h2>Calibration Snapshot</h2>
              <span>Most recent run metadata</span>
            </div>
            {calibrationResult ? (
              <dl className="key-value">
                <div>
                  <dt>Run ID</dt>
                  <dd>{calibrationResult.run_id.slice(0, 8)}</dd>
                </div>
                <div>
                  <dt>Timestamp</dt>
                  <dd>{toLocalTimestamp(calibrationResult.timestamp)}</dd>
                </div>
                <div>
                  <dt>Prompts Tested</dt>
                  <dd>{calibrationResult.prompts_count}</dd>
                </div>
                <div>
                  <dt>Regret Rate</dt>
                  <dd>{(calibrationResult.regret_rate * 100).toFixed(1)}%</dd>
                </div>
                <div>
                  <dt>Savings vs Baseline</dt>
                  <dd>{(calibrationResult.cost_vs_baseline * 100).toFixed(1)}%</dd>
                </div>
              </dl>
            ) : (
              <p className="empty">Run calibration to populate this panel.</p>
            )}
          </article>

          <article className="panel panel-roadmap">
            <div className="panel-header">
              <h2>Win Rate by Task</h2>
              <span>Classification accuracy from latest calibration run</span>
            </div>
            {calibrationResult ? (
              <div className="task-bars">
                {Object.entries(calibrationResult.win_rate_by_task).map(([task, metrics]) => (
                  <div key={task} className="task-row">
                    <div className="task-label">
                      <strong>{task}</strong>
                      <span>{(metrics.classification_accuracy * 100).toFixed(1)}%</span>
                    </div>
                    <div className="task-track">
                      <div
                        className="task-fill"
                        style={{ width: `${Math.min(100, metrics.classification_accuracy * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty">No run data yet.</p>
            )}
          </article>
        </section>
      ) : null}

      {activeSection === "timeline" ? (
        <section className="grid">
          <article className="panel panel-playground">
            <div className="panel-header">
              <h2>Request Timeline</h2>
              <span>Filter and inspect live routing records</span>
            </div>
            <form className="timeline-filters" onSubmit={submitTimelineFilters}>
              <label>
                Model
                <select value={timelineModel} onChange={(event) => setTimelineModel(event.target.value)}>
                  <option value="all">All</option>
                  {providersForFilter.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Task Type
                <select value={timelineTaskType} onChange={(event) => setTimelineTaskType(event.target.value)}>
                  <option value="all">All</option>
                  <option value="reasoning">reasoning</option>
                  <option value="knowledge_work">knowledge_work</option>
                  <option value="code">code</option>
                  <option value="extraction">extraction</option>
                  <option value="creative">creative</option>
                  <option value="general">general</option>
                </select>
              </label>
              <label>
                Cache Hit
                <select value={timelineCacheHit} onChange={(event) => setTimelineCacheHit(event.target.value)}>
                  <option value="all">All</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label>
                Fallback
                <select value={timelineFallback} onChange={(event) => setTimelineFallback(event.target.value)}>
                  <option value="all">All</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label>
                Page Size
                <select
                  value={timelineLimit}
                  onChange={(event) => setTimelineLimit(Number(event.target.value))}
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                </select>
              </label>
              <button type="submit" disabled={loadingTimeline}>
                {loadingTimeline ? "Refreshing..." : "Apply Filters"}
              </button>
            </form>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Model</th>
                    <th>Task</th>
                    <th>Cost</th>
                    <th>Latency</th>
                    <th>Cache</th>
                    <th>Fallback</th>
                  </tr>
                </thead>
                <tbody>
                  {timeline.items.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="empty-row">
                        {loadingTimeline ? "Loading..." : "No matching request records."}
                      </td>
                    </tr>
                  ) : (
                    timeline.items.map((entry) => (
                      <tr key={entry.id}>
                        <td>{toLocalTimestamp(entry.timestamp)}</td>
                        <td className="mono">{entry.model_used}</td>
                        <td>{entry.task_type}</td>
                        <td>{toUsd(entry.cost)}</td>
                        <td>{entry.latency_ms} ms</td>
                        <td>{entry.cache_hit ? "Yes" : "No"}</td>
                        <td>{entry.fallback_triggered ? "Yes" : "No"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="pager">
              <span>
                Showing {timeline.items.length} of {timeline.total}
              </span>
              <div className="pager-actions">
                <button
                  type="button"
                  className="ghost"
                  disabled={timelineOffset === 0 || loadingTimeline}
                  onClick={() => void refreshTimeline(Math.max(0, timelineOffset - timelineLimit), timelineLimit)}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={timelineOffset + timelineLimit >= timeline.total || loadingTimeline}
                  onClick={() => void refreshTimeline(timelineOffset + timelineLimit, timelineLimit)}
                >
                  Next
                </button>
              </div>
            </div>
          </article>
        </section>
      ) : null}
    </main>
  );
}
