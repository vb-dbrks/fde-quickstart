import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  idempotencyKey,
  unwrap,
  type Access,
  type AgentRun,
  type AgentRunCreate,
  type Role,
} from "@/lib/api";

/** How often the bell polls for notifications. The Apps proxy buffers server-sent events. */
export const NOTIFICATION_POLL_MS = 30_000;

export const queryKeys = {
  health: ["health"],
  me: ["me"],
  notifications: ["notifications"],
  roles: ["admin", "roles"],
  roleAssignments: ["admin", "role-assignments"],
  documentTypes: ["document-types"],
  documents: ["documents"],
  // Everything below a document shares the ["document", id] prefix, so one invalidation refreshes
  // its fields, history, access list and conversations.
  document: (id: string) => ["document", id],
  versions: (id: string) => ["document", id, "versions"],
  audit: (id: string) => ["document", id, "audit"],
  access: (id: string) => ["document", id, "access"],
  runs: (id: string) => ["document", id, "runs"],
  threads: (id: string) => ["document", id, "threads"],
  messages: (threadId: string) => ["thread", threadId, "messages"],
  agentRun: (runId: string) => ["agent-run", runId],
} as const;

export function useHealth() {
  return useQuery({ queryKey: queryKeys.health, queryFn: () => unwrap(api.GET("/api/health")) });
}

export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: () => unwrap(api.GET("/api/me")),
    staleTime: 60_000,
  });
}

// ---- documents --------------------------------------------------------------------------------

export function useDocumentTypes() {
  return useQuery({
    queryKey: queryKeys.documentTypes,
    queryFn: () => unwrap(api.GET("/api/document-types")),
    staleTime: Infinity,
  });
}

export function useDocuments() {
  return useQuery({
    queryKey: queryKeys.documents,
    queryFn: () => unwrap(api.GET("/api/documents")),
  });
}

export function useDocument(documentId: string) {
  return useQuery({
    queryKey: queryKeys.document(documentId),
    queryFn: () =>
      unwrap(
        api.GET("/api/documents/{document_id}", { params: { path: { document_id: documentId } } }),
      ),
  });
}

export function useCreateDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { document_type: string; fields: Record<string, unknown> }) =>
      unwrap(
        api.POST("/api/documents", { body, headers: { "Idempotency-Key": idempotencyKey() } }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.documents }),
  });
}

export function useUpdateField(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      fieldPath,
      value,
      acceptedFromRunId,
    }: {
      fieldPath: string;
      value: unknown;
      acceptedFromRunId?: string;
    }) =>
      unwrap(
        api.PATCH("/api/documents/{document_id}/fields/{field_path}", {
          params: { path: { document_id: documentId, field_path: fieldPath } },
          body: { value, accepted_from_run_id: acceptedFromRunId ?? null },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.document(documentId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents });
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      unwrap(
        api.DELETE("/api/documents/{document_id}", {
          params: { path: { document_id: documentId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.documents }),
  });
}

export function useVersions(documentId: string) {
  return useQuery({
    queryKey: queryKeys.versions(documentId),
    queryFn: () =>
      unwrap(
        api.GET("/api/documents/{document_id}/versions", {
          params: { path: { document_id: documentId } },
        }),
      ),
  });
}

export function useAudit(documentId: string) {
  return useQuery({
    queryKey: queryKeys.audit(documentId),
    queryFn: () =>
      unwrap(
        api.GET("/api/documents/{document_id}/audit", {
          params: { path: { document_id: documentId } },
        }),
      ),
  });
}

export function useAgentRuns(documentId: string) {
  return useQuery({
    queryKey: queryKeys.runs(documentId),
    queryFn: () =>
      unwrap(
        api.GET("/api/documents/{document_id}/agent-runs", {
          params: { path: { document_id: documentId } },
        }),
      ),
  });
}

// ---- sharing ----------------------------------------------------------------------------------

export function useDocumentAccess(documentId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.access(documentId),
    queryFn: () =>
      unwrap(
        api.GET("/api/documents/{document_id}/access", {
          params: { path: { document_id: documentId } },
        }),
      ),
    enabled,
  });
}

export function useShareDocument(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; access: Access }) =>
      unwrap(
        api.PUT("/api/documents/{document_id}/access", {
          params: { path: { document_id: documentId } },
          body,
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.access(documentId) }),
  });
}

export function useUnshareDocument(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (email: string) =>
      unwrap(
        api.DELETE("/api/documents/{document_id}/access/{email}", {
          params: { path: { document_id: documentId, email } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.access(documentId) }),
  });
}

// ---- agent runs and conversations -------------------------------------------------------------

/** Start an agent run; follow it with useAgentRun (lib/agentRuns.ts). */
export function useStartAgentRun(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AgentRunCreate) =>
      unwrap(
        api.POST("/api/documents/{document_id}/agent-runs", {
          params: {
            path: { document_id: documentId },
            header: { "Idempotency-Key": idempotencyKey() },
          },
          body,
        }),
      ),
    onSuccess: (run: AgentRun) => {
      queryClient.setQueryData(queryKeys.agentRun(run.id), run);
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs(documentId) });
      // The user's chat message is stored when the run starts.
      if (run.thread_id) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.messages(run.thread_id) });
      }
    },
  });
}

export function useThreads(documentId: string) {
  return useQuery({
    queryKey: queryKeys.threads(documentId),
    queryFn: () =>
      unwrap(
        api.GET("/api/documents/{document_id}/threads", {
          params: { path: { document_id: documentId } },
        }),
      ),
  });
}

export function useCreateThread(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) =>
      unwrap(
        api.POST("/api/documents/{document_id}/threads", {
          params: { path: { document_id: documentId } },
          body: { title: title ?? "Conversation" },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.threads(documentId) }),
  });
}

export function useMessages(threadId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.messages(threadId ?? ""),
    queryFn: () =>
      unwrap(
        api.GET("/api/threads/{thread_id}/messages", {
          params: { path: { thread_id: threadId ?? "" } },
        }),
      ),
    enabled: Boolean(threadId),
  });
}

// ---- notifications ----------------------------------------------------------------------------

export function useNotifications() {
  return useQuery({
    queryKey: queryKeys.notifications,
    queryFn: () => unwrap(api.GET("/api/notifications", { params: { query: { limit: 10 } } })),
    refetchInterval: NOTIFICATION_POLL_MS,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: number) =>
      unwrap(
        api.POST("/api/notifications/{notification_id}/read", {
          params: { path: { notification_id: notificationId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.notifications }),
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/notifications/read-all")),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.notifications }),
  });
}

// ---- admin ------------------------------------------------------------------------------------

export function useRoles() {
  return useQuery({
    queryKey: queryKeys.roles,
    queryFn: () => unwrap(api.GET("/api/admin/roles")),
  });
}

export function useRoleAssignments() {
  return useQuery({
    queryKey: queryKeys.roleAssignments,
    queryFn: () => unwrap(api.GET("/api/admin/role-assignments")),
  });
}

export function useGrantRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; role: Role }) =>
      unwrap(api.POST("/api/admin/role-assignments", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.roleAssignments }),
  });
}

export function useRevokeRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ email, role }: { email: string; role: Role }) =>
      unwrap(
        api.DELETE("/api/admin/role-assignments/{email}/{role}", {
          params: { path: { email, role } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.roleAssignments }),
  });
}
