import { useEffect, useRef } from "react";
import { post, request } from "@/agent/transport";
import type { Interaction } from "@/agent/AgentProvider";

export type FrontendTool = { execute: (args: Record<string, unknown>) => void };
export function ToolActions({
  runId,
  interaction,
  tools,
}: {
  runId: string;
  interaction: Interaction;
  tools: Record<string, FrontendTool>;
}) {
  const handled = useRef(new Set<string>());
  useEffect(() => {
    if (!interaction.finished || interaction.error) return;
    let disposed = false;
    async function apply() {
      const existing = new Set(await request<string[]>(`/runs/${runId}/tools`));
      const calls = new Map<string, { name: string; args: string; complete: boolean }>();
      for (const event of interaction.toolEvents) {
        const id = String(event.toolCallId ?? "");
        if (event.type === "TOOL_CALL_START")
          calls.set(id, { name: String(event.toolCallName), args: "", complete: false });
        const call = calls.get(id);
        if (call && event.type === "TOOL_CALL_ARGS") call.args += String(event.delta);
        if (call && event.type === "TOOL_CALL_END") call.complete = true;
      }
      for (const [id, call] of calls) {
        if (
          disposed ||
          !call.complete ||
          existing.has(id) ||
          handled.current.has(id) ||
          !tools[call.name]
        )
          continue;
        const args = JSON.parse(call.args) as Record<string, unknown>;
        handled.current.add(id);
        const claim = await post<{ execute: boolean }>(`/runs/${runId}/tools/${id}/claim`, {});
        if (!claim.execute) continue;
        tools[call.name]?.execute(args);
        await post(`/runs/${runId}/tools/${id}`, { status: "completed" }, `${runId}:${id}`);
      }
    }
    void apply().catch(() => {
      /* A UI action is optional; the validated result remains available. */
    });
    return () => {
      disposed = true;
    };
  }, [runId, interaction, tools]);
  return null;
}
