import { useMemo } from "react";

import type { Permission } from "@/lib/api";
import { useMe } from "@/lib/queries";

/**
 * The signed-in user's permissions, from GET /api/me. Use it to hide actions the user can't take;
 * the backend enforces the same permissions on every request.
 */
export function usePermissions() {
  const me = useMe();
  const granted = useMemo(() => new Set(me.data?.permissions ?? []), [me.data]);
  return {
    me: me.data,
    isLoading: me.isPending,
    can: (permission: Permission) => granted.has(permission),
  };
}
