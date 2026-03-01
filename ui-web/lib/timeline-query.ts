export type TimelineFilterInput = {
  offset: number;
  limit: number;
  model: string;
  taskType: string;
  cacheHit: string;
  fallbackTriggered: string;
};

export function buildTimelineQuery(filters: TimelineFilterInput): string {
  const params = new URLSearchParams();
  params.set("offset", String(filters.offset));
  params.set("limit", String(filters.limit));

  if (filters.model !== "all") {
    params.set("model", filters.model);
  }
  if (filters.taskType !== "all") {
    params.set("task_type", filters.taskType);
  }
  if (filters.cacheHit !== "all") {
    params.set("cache_hit", filters.cacheHit);
  }
  if (filters.fallbackTriggered !== "all") {
    params.set("fallback_triggered", filters.fallbackTriggered);
  }

  return params.toString();
}
