import { afterEach, describe, expect, it, vi } from "vitest";
import { DurableAgent } from "@/agent/transport";
import type { BaseEvent } from "@ag-ui/core";

const start = { sequence: 1, event: { type: "RUN_STARTED", runId: "r", threadId: "r" } };
const state = {
  sequence: 2,
  event: { type: "STATE_SNAPSHOT", snapshot: { preview: { title: "Draft" }, provisional: true } },
};
const end = { sequence: 3, event: { type: "RUN_FINISHED", runId: "r", threadId: "r" } };
const frame = (value: unknown) => `data: ${JSON.stringify(value)}\n\n`;
const follow = async () => {
  const events: BaseEvent[] = [];
  const agent = new DurableAgent("r");
  await agent.runAgent(
    { runId: "r" },
    {
      onEvent: ({ event }) => {
        events.push(event);
      },
    },
  );
  return { agent, events };
};
afterEach(() => {
  vi.useRealTimers();
});

describe("durable AG-UI transport", () => {
  it("recovers an interrupted SSE from the cursor, ignores duplicate events and never submits", async () => {
    const fetcher = vi.fn(async (request: Request) => {
      if (request.headers.get("Accept") === "text/event-stream")
        return new Response(frame(start) + frame(state));
      expect(new URL(request.url).searchParams.get("after")).toBe("2");
      return Response.json({ events: [state, end], cursor: 3, terminal: true });
    });
    vi.stubGlobal("fetch", fetcher);
    const { agent, events } = await follow();
    expect(events.map((event) => event.type)).toEqual([
      "RUN_STARTED",
      "STATE_SNAPSHOT",
      "RUN_FINISHED",
    ]);
    expect(agent.state).toEqual(state.event.snapshot);
    expect(fetcher.mock.calls.map(([request]) => request.method)).toEqual(["GET", "GET"]);
    await follow(); // Reload reconstructs the same interaction, without a second model request.
    expect(fetcher).toHaveBeenCalledTimes(4);
  });

  it("falls back after missing heartbeats and stays on polling", async () => {
    vi.useFakeTimers();
    let polls = 0;
    const fetcher = vi.fn(async (request: Request) => {
      if (request.headers.get("Accept") === "text/event-stream") {
        return new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(new TextEncoder().encode(frame(start)));
              request.signal.addEventListener("abort", () =>
                controller.error(new Error("aborted")),
              );
            },
          }),
        );
      }
      return Response.json(
        ++polls === 1
          ? { events: [state], cursor: 2, terminal: false }
          : { events: [end], cursor: 3, terminal: true },
      );
    });
    vi.stubGlobal("fetch", fetcher);
    const result = follow();
    await vi.advanceTimersByTimeAsync(16010);
    expect((await result).events).toHaveLength(3);
    expect(fetcher.mock.calls.filter(([request]) => request.headers.has("Accept"))).toHaveLength(1);
    expect(polls).toBe(2);
  });

  it("does not poll after access is revoked", async () => {
    const fetcher = vi.fn(async () => new Response("event: access-denied\ndata: {}\n\n"));
    vi.stubGlobal("fetch", fetcher);
    await expect(follow()).rejects.toThrow("Access to this interaction changed");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
