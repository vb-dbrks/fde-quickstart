import { ShieldX } from "lucide-react";
import type { ReactNode } from "react";

import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import type { Permission } from "@/lib/api";
import { usePermissions } from "@/lib/permissions";

/** Route guard: shows a "no access" page unless the user has ``permission``. */
export function RequirePermission({
  permission,
  children,
}: {
  permission: Permission;
  children: ReactNode;
}) {
  const { can, isLoading } = usePermissions();
  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (!can(permission)) {
    return (
      <EmptyState
        icon={ShieldX}
        title="You don't have access to this page"
        description={
          <>
            Ask an admin for a role that includes <code>{permission}</code>.
          </>
        }
      />
    );
  }
  return children;
}
