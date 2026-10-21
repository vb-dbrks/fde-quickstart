import { FileText } from "lucide-react";
import { Link } from "react-router";

import { Can } from "@/components/Can";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { QueryError } from "@/components/QueryError";
import { NewDocumentDialog } from "@/components/documents/NewDocumentDialog";
import { ACCESS_LABELS } from "@/components/documents/values";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatRelative } from "@/lib/format";
import { useDocumentTypes, useDocuments } from "@/lib/queries";

/** The documents you own or that are shared with you. */
export function DocumentsPage() {
  const documents = useDocuments();
  const types = useDocumentTypes();
  const typeLabels = new Map(types.data?.map((type) => [type.name, type.label]));

  return (
    <>
      <PageHeader
        title="Documents"
        description="Documents you own or that are shared with you. The agent drafts their fields."
        actions={
          <Can permission="documents:create">
            {types.data?.map((type) => (
              <NewDocumentDialog key={type.name} documentType={type} />
            ))}
          </Can>
        }
      />
      {documents.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : documents.isError ? (
        <QueryError error={documents.error} onRetry={() => documents.refetch()} />
      ) : documents.data.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Create one, or ask a colleague to share theirs with you."
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Your access</TableHead>
              <TableHead>Version</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.data.map((document) => (
              <TableRow key={document.id}>
                <TableCell>
                  <Link
                    to={`/documents/${document.id}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    {document.title}
                  </Link>
                </TableCell>
                <TableCell>
                  {typeLabels.get(document.document_type) ?? document.document_type}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{ACCESS_LABELS[document.my_access]}</Badge>
                </TableCell>
                <TableCell>{document.current_version || "—"}</TableCell>
                <TableCell className="text-muted-foreground">
                  {formatRelative(document.updated_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}
