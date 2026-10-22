/** Persisted application data stays in TanStack Query; active state lives in AgentProvider. */
import { useQuery } from "@tanstack/react-query";
import type { components } from "@/api/schema";
import { request } from "@/agent/transport";

export const sessionKeys = {
  list: (agentId: string) => ["sessions", agentId] as const,
  messages: (sessionId?: string | null) => ["session-messages", sessionId] as const,
};
export const runKey = (agentId: string, sessionId?: string | null) =>
  ["runs", agentId, sessionId] as const;
export function useSessions(agentId: string) {
  return useQuery({
    queryKey: sessionKeys.list(agentId),
    queryFn: () =>
      request<components["schemas"]["SessionOut"][]>(
        `/sessions?agent_id=${encodeURIComponent(agentId)}`,
      ),
  });
}
export function useSessionMessages(sessionId?: string | null) {
  return useQuery({
    queryKey: sessionKeys.messages(sessionId),
    queryFn: () =>
      request<components["schemas"]["MessageOut"][]>(`/sessions/${sessionId}/messages`),
    enabled: !!sessionId,
  });
}
export function useRuns(agentId: string, sessionId?: string | null, enabled = true) {
  return useQuery({
    queryKey: runKey(agentId, sessionId),
    queryFn: () =>
      request<components["schemas"]["InteractionOut"][]>(
        `/runs?agent_id=${encodeURIComponent(agentId)}${sessionId ? `&session_id=${encodeURIComponent(sessionId)}` : ""}`,
      ),
    enabled,
  });
}
