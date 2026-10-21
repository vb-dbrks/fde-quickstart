import { QueryError } from "@/components/QueryError";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { DocumentField } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useAudit, useVersions } from "@/lib/queries";

const ACTION_LABELS: Record<string, string> = {
  create: "Created",
  update: "Edited",
  generate: "Generated",
  regenerate: "Regenerated",
  accept_suggestion: "Accepted suggestion",
  share: "Shared",
  unshare: "Unshared",
  delete: "Deleted",
};

/** Versions (one per agent generation) and the field-level audit trail. */
export function HistoryPanel({
  documentId,
  fields,
}: {
  documentId: string;
  fields: DocumentField[];
}) {
  const versions = useVersions(documentId);
  const audit = useAudit(documentId);
  const labels = new Map(fields.map((field) => [field.field_path, field.label]));

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
      <Card>
        <CardHeader>
          <CardTitle>Versions</CardTitle>
          <CardDescription>A snapshot is taken each time the agent generates.</CardDescription>
        </CardHeader>
        <CardContent>
          {versions.isPending ? (
            <Skeleton className="h-20 w-full" />
          ) : versions.isError ? (
            <QueryError error={versions.error} onRetry={() => versions.refetch()} />
          ) : versions.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">No versions yet.</p>
          ) : (
            <ol className="space-y-2 text-sm">
              {versions.data.map((version) => (
                <li key={version.version} className="flex items-center justify-between gap-2">
                  <Badge variant="outline">v{version.version}</Badge>
                  <span className="text-muted-foreground">
                    {version.created_by} · {formatDateTime(version.created_at)}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Audit trail</CardTitle>
          <CardDescription>Every change to a field, by a person or the agent.</CardDescription>
        </CardHeader>
        <CardContent>
          {audit.isPending ? (
            <Skeleton className="h-20 w-full" />
          ) : audit.isError ? (
            <QueryError error={audit.error} onRetry={() => audit.refetch()} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Who</TableHead>
                  <TableHead>What</TableHead>
                  <TableHead>Field</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {audit.data.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="text-muted-foreground">
                      {formatDateTime(entry.created_at)}
                    </TableCell>
                    <TableCell>{entry.actor}</TableCell>
                    <TableCell>{ACTION_LABELS[entry.action] ?? entry.action}</TableCell>
                    <TableCell>
                      {entry.field_path ? (labels.get(entry.field_path) ?? entry.field_path) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
