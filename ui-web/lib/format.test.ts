import { describe, expect, it } from "vitest";

import { toLocalTimestamp, toUsd } from "./format";

describe("format helpers", () => {
  it("formats USD with fixed precision", () => {
    expect(toUsd(1.2)).toBe("$1.200000");
    expect(toUsd(0)).toBe("$0.000000");
  });

  it("returns input string for invalid timestamp", () => {
    const input = "not-a-date";
    expect(toLocalTimestamp(input)).toBe(input);
  });

  it("formats valid ISO timestamp as local date-time string", () => {
    const iso = "2026-01-15T12:34:56Z";
    const formatted = toLocalTimestamp(iso);

    expect(formatted).not.toBe(iso);
    expect(formatted.length).toBeGreaterThan(0);
  });
});
