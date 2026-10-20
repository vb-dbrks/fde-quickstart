import type { ReactNode } from "react";

import type { Permission } from "@/lib/api";
import { usePermissions } from "@/lib/permissions";

/** Render ``children`` only if the user has ``permission``; the API enforces it regardless. */
export function Can({
  permission,
  children,
  fallback = null,
}: {
  permission: Permission;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { can } = usePermissions();
  return <>{can(permission) ? children : fallback}</>;
}
