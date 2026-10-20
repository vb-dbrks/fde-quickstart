import { UserX } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { QueryError } from "@/components/QueryError";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Role } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useGrantRole, useRevokeRole, useRoleAssignments, useRoles } from "@/lib/queries";

/** Admin page (requires roles:manage): grant and revoke roles. */
export function AdminRolesPage() {
  return (
    <>
      <PageHeader
        title="Users & roles"
        description="Everyone who can open the app is a viewer. Grant extra roles here."
      />
      <GrantRoleForm />
      <Assignments />
      <RoleCatalog />
    </>
  );
}

function GrantRoleForm() {
  const roles = useRoles();
  const grant = useGrantRole();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("editor");

  function submit(event: FormEvent) {
    event.preventDefault();
    grant.mutate(
      { email, role },
      {
        onSuccess: () => {
          toast.success(`Granted ${role} to ${email}`);
          setEmail("");
        },
        onError: (error) => toast.error(error.message),
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Grant a role</CardTitle>
        <CardDescription>The user is notified in the app.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1 space-y-1.5">
            <Label htmlFor="grant-email">Email</Label>
            <Input
              id="grant-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="grant-role">Role</Label>
            <select
              id="grant-role"
              value={role}
              onChange={(event) => setRole(event.target.value as Role)}
              className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs dark:bg-input/30"
            >
              {(roles.data ?? []).map((item) => (
                <option key={item.role} value={item.role}>
                  {item.role}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" disabled={grant.isPending}>
            Grant
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function Assignments() {
  const assignments = useRoleAssignments();
  const revoke = useRevokeRole();

  if (assignments.isPending) return <Skeleton className="h-32 w-full" />;
  if (assignments.isError) {
    return <QueryError error={assignments.error} onRetry={() => assignments.refetch()} />;
  }
  if (assignments.data.length === 0) {
    return (
      <EmptyState
        icon={UserX}
        title="No roles granted yet"
        description="Admins listed in the app's configuration are admins without an entry here."
      />
    );
  }
  return (
    <Card>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Granted by</TableHead>
              <TableHead>Granted</TableHead>
              <TableHead>
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {assignments.data.map((assignment) => (
              <TableRow key={`${assignment.principal}/${assignment.role}`}>
                <TableCell>{assignment.principal}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{assignment.role}</Badge>
                </TableCell>
                <TableCell>{assignment.granted_by}</TableCell>
                <TableCell>{formatDateTime(assignment.granted_at)}</TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={revoke.isPending}
                    onClick={() =>
                      revoke.mutate(
                        { email: assignment.principal, role: assignment.role },
                        { onError: (error) => toast.error(error.message) },
                      )
                    }
                  >
                    Revoke
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function RoleCatalog() {
  const roles = useRoles();
  if (!roles.data) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>What each role can do</CardTitle>
        <CardDescription>Defined in backend/app/permissions/roles.py.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {roles.data.map((item) => (
          <div key={item.role} className="flex flex-wrap items-center gap-2">
            <Badge>{item.role}</Badge>
            {item.permissions.map((permission) => (
              <Badge key={permission} variant="outline">
                {permission}
              </Badge>
            ))}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
