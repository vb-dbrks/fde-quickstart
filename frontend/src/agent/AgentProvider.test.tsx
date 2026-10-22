import { StrictMode } from "react";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { AgentProvider, useInteraction } from "@/agent/AgentProvider";

it("reattaches safely after StrictMode cleanup without submitting another run", async () => {
  const fetcher = vi.fn(
    async () =>
      new Response(
        [
          { type: "RUN_STARTED", runId: "r", threadId: "r" },
          { type: "STATE_SNAPSHOT", snapshot: { title: "Recovered" } },
          { type: "RUN_FINISHED", runId: "r", threadId: "r" },
        ]
          .map((event, i) => `data: ${JSON.stringify({ sequence: i + 1, event })}\n\n`)
          .join(""),
      ),
  );
  vi.stubGlobal("fetch", fetcher);
  function View() {
    const interaction = useInteraction("r");
    return (
      <p>
        {interaction.error ?? (interaction.finished ? String(interaction.state.title) : "Loading")}
      </p>
    );
  }
  render(
    <StrictMode>
      <AgentProvider>
        <View />
      </AgentProvider>
    </StrictMode>,
  );
  expect(await screen.findByText("Recovered")).toBeVisible();
  expect(fetcher).toHaveBeenCalledTimes(2);
});
