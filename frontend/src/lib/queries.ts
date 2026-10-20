import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type NoteIn, type Role } from "@/lib/api";

/** How often the bell polls for notifications. The Apps proxy buffers server-sent events. */
export const NOTIFICATION_POLL_MS = 30_000;

export const queryKeys = {
  health: ["health"],
  me: ["me"],
  notes: (mine: boolean) => ["notes", { mine }],
  allNotes: ["notes"],
  notifications: ["notifications"],
  agents: ["agents"],
  roles: ["admin", "roles"],
  roleAssignments: ["admin", "role-assignments"],
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

export function useNotes(mine = false) {
  return useQuery({
    queryKey: queryKeys.notes(mine),
    queryFn: () => unwrap(api.GET("/api/notes", { params: { query: { mine } } })),
  });
}

export function useCreateNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: NoteIn) => unwrap(api.POST("/api/notes", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.allNotes }),
  });
}

export function useDeleteNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (noteId: number) =>
      unwrap(api.DELETE("/api/notes/{note_id}", { params: { path: { note_id: noteId } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.allNotes }),
  });
}

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

export function useAgents() {
  return useQuery({ queryKey: queryKeys.agents, queryFn: () => unwrap(api.GET("/api/agents")) });
}

export function useInvokeAgent(name: string) {
  return useMutation({
    mutationFn: (message: string) =>
      unwrap(
        api.POST("/api/agents/{name}/invoke", { params: { path: { name } }, body: { message } }),
      ),
  });
}

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
