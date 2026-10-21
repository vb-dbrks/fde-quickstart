import { FileText, ShieldCheck } from "lucide-react";
import { Link } from "react-router";

import { Can } from "@/components/Can";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Health } from "@/lib/api";
import { usePermissions } from "@/lib/permissions";
import { useHealth } from "@/lib/queries";

export function HomePage() {
  const { me } = usePermissions();
  const health = useHealth();

  return (
    <>
      <PageHeader
        title={me ? `Welcome, ${me.display_name}` : "Welcome"}
        description="A Databricks App: FastAPI and React, Lakebase as the system of record, and a stateless agent behind a versioned contract."
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
            <CardDescription>
              The database and the agent each run kind is served by.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {health.isPending ? (
              <Skeleton className="h-6 w-32" />
            ) : (
              <>
                <Badge variant={health.data?.database === "ok" ? "secondary" : "destructive"}>
                  Database: {health.data?.database === "ok" ? "connected" : "unavailable"}
                </Badge>
                <AgentStatus agent={health.data?.agent} />
              </>
            )}
          </CardContent>
        </Card>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline">
          <Link to="/documents">
            <FileText aria-hidden /> Documents
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

function AgentStatus({ agent }: { agent: Health["agent"] }) {
  if (!agent) return null;
  const runners = (agent.runners ?? {}) as Record<string, string>;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      <dt className="text-muted-foreground">Agent transport</dt>
      <dd>{String(agent.transport)}</dd>
      {Object.entries(runners).map(([kind, runner]) => (
        <div key={kind} className="contents">
          <dt className="text-muted-foreground">{kind}</dt>
          <dd>
            <Badge variant={runner === "fake" ? "outline" : "secondary"}>{runner}</Badge>
          </dd>
        </div>
      ))}
    </dl>
  );
}
