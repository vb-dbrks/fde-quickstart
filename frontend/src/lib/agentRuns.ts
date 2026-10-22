import { useInteraction } from "@/agent/AgentProvider";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api, ApiError, unwrap, type AgentRun, type RunStatus } from "@/lib/api";
import { queryKeys } from "@/lib/queries";

/**
 * Polling schedule for an agent run: quick at first, then backing off. The Apps proxy buffers
 * server-sent events and times requests out after 120 s, so the UI polls instead of streaming.
 * Each poll also lets the backend refresh the run from the agent (lazy refresh).
 */
export const RUN_POLL = { initialMs: 1_500, factor: 1.5, maxMs: 10_000 } as const;

export function pollDelay(attempt: number): number {
  return Math.min(RUN_POLL.maxMs, Math.round(RUN_POLL.initialMs * RUN_POLL.factor ** attempt));
}

export function isTerminal(status: RunStatus): boolean {
  return status === "succeeded" || status === "failed";
}

/**
 * Follow an agent run until it succeeds or fails. When it finishes, the document, its history and
 * the notification bell are refreshed (the backend has materialised the output by then), and
 * ``onSettled`` is called once.
 */
export function useAgentRun(
  runId: string | null | undefined,
  { onSettled }: { onSettled?: (run: AgentRun) => void } = {},
) {
  const queryClient = useQueryClient();
  const interaction = useInteraction(runId);
  useEffect(() => {
    if (runId && interaction.finished) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.agentRun(runId) });
      void queryClient.invalidateQueries({ queryKey: ["document-proposals"] });
    }
  }, [runId, interaction.finished, queryClient]);
  const query = useQuery({
    queryKey: queryKeys.agentRun(runId ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/agent-runs/{run_id}", { params: { path: { run_id: runId ?? "" } } })),
    enabled: Boolean(runId),
    refetchInterval: ({ state }) => {
      if (state.data && isTerminal(state.data.status)) return false;
      // A failed poll (a blip, the app restarting) keeps polling; a run we may not see does not.
      if (state.error instanceof ApiError && [403, 404].includes(state.error.status)) return false;
      return pollDelay(Math.max(0, state.dataUpdateCount + state.errorUpdateCount - 1));
    },
    refetchIntervalInBackground: true,
  });

  const run = query.data;
  const settled = useRef<string | null>(null);
  const onSettledRef = useRef(onSettled);
  useEffect(() => {
    onSettledRef.current = onSettled;
  });

  useEffect(() => {
    if (!run || !isTerminal(run.status) || settled.current === run.id) return;
    settled.current = run.id;
    void queryClient.invalidateQueries({ queryKey: queryKeys.document(run.document_id) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.documents });
    void queryClient.invalidateQueries({ queryKey: ["document-proposals"] });
    void queryClient.invalidateQueries({ queryKey: queryKeys.notifications });
    if (run.thread_id) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.messages(run.thread_id) });
    }
    onSettledRef.current?.(run);
  }, [run, queryClient]);

  return query;
}
