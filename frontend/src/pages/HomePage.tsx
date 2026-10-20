import { Bot, ShieldCheck, StickyNote } from "lucide-react";
import { Link } from "react-router";

import { Can } from "@/components/Can";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePermissions } from "@/lib/permissions";
import { useHealth } from "@/lib/queries";

export function HomePage() {
  const { me } = usePermissions();
  const health = useHealth();

  return (
    <>
      <PageHeader
        title={me ? `Welcome, ${me.display_name}` : "Welcome"}
        description="A starting point for your Databricks App: FastAPI, React and Lakebase Postgres."
      />
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Your access</CardTitle>
            <CardDescription>Roles are granted by admins under Users &amp; roles.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {me ? (
              <>
                <div className="flex flex-wrap gap-1">
                  {me.roles.map((role) => (
                    <Badge key={role}>{role}</Badge>
                  ))}
                </div>
                <ul className="flex flex-wrap gap-1">
                  {me.permissions.map((permission) => (
                    <li key={permission}>
                      <Badge variant="outline">{permission}</Badge>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <Skeleton className="h-12 w-full" />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>System status</CardTitle>
            <CardDescription>The API and its Lakebase database.</CardDescription>
          </CardHeader>
          <CardContent>
            {health.isPending ? (
              <Skeleton className="h-6 w-32" />
            ) : (
              <Badge variant={health.data?.database === "ok" ? "secondary" : "destructive"}>
                Database: {health.data?.database === "ok" ? "connected" : "unavailable"}
              </Badge>
            )}
          </CardContent>
        </Card>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline">
          <Link to="/notes">
            <StickyNote aria-hidden /> Notes
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/assistant">
            <Bot aria-hidden /> Assistant
          </Link>
        </Button>
        <Can permission="roles:manage">
          <Button asChild variant="outline">
            <Link to="/admin/roles">
              <ShieldCheck aria-hidden /> Users &amp; roles
            </Link>
          </Button>
        </Can>
      </div>
    </>
  );
}
