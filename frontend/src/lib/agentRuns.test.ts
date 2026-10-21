import { describe, expect, it } from "vitest";

import { isTerminal, pollDelay, RUN_POLL } from "@/lib/agentRuns";

describe("agent run polling", () => {
  it("starts quickly and backs off to the cap", () => {
    const delays = Array.from({ length: 8 }, (_, attempt) => pollDelay(attempt));
    expect(delays[0]).toBe(RUN_POLL.initialMs);
    expect(delays).toEqual([...delays].sort((a, b) => a - b));
    expect(delays.at(-1)).toBe(RUN_POLL.maxMs);
  });

  it("stops at succeeded or failed", () => {
    expect(isTerminal("succeeded")).toBe(true);
    expect(isTerminal("failed")).toBe(true);
    expect(isTerminal("queued")).toBe(false);
    expect(isTerminal("accepted")).toBe(false);
    expect(isTerminal("running")).toBe(false);
  });
});
