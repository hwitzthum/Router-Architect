import { describe, expect, it } from "vitest";

import { buildTimelineQuery } from "./timeline-query";

describe("buildTimelineQuery", () => {
  it("includes pagination and explicit filters", () => {
    const query = buildTimelineQuery({
      offset: 50,
      limit: 25,
      model: "gpt-4o-mini",
      taskType: "code",
      cacheHit: "true",
      fallbackTriggered: "false"
    });
    const params = new URLSearchParams(query);

    expect(params.get("offset")).toBe("50");
    expect(params.get("limit")).toBe("25");
    expect(params.get("model")).toBe("gpt-4o-mini");
    expect(params.get("task_type")).toBe("code");
    expect(params.get("cache_hit")).toBe("true");
    expect(params.get("fallback_triggered")).toBe("false");
  });

  it("omits optional filters when set to all", () => {
    const query = buildTimelineQuery({
      offset: 0,
      limit: 10,
      model: "all",
      taskType: "all",
      cacheHit: "all",
      fallbackTriggered: "all"
    });

    expect(query).toBe("offset=0&limit=10");
  });
});
