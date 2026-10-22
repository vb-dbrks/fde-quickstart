import { ProposalsPanel } from "@/components/documents/ProposalsPanel";
import { FileQuestion } from "lucide-react";
import { useParams, useSearchParams } from "react-router";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { QueryError } from "@/components/QueryError";
import { AssistantPanel } from "@/components/documents/AssistantPanel";
import { DeleteDocumentButton } from "@/components/documents/DeleteDocumentButton";
import { FieldCard } from "@/components/documents/FieldCard";
import { GeneratePanel } from "@/components/documents/GeneratePanel";
import { HistoryPanel } from "@/components/documents/HistoryPanel";
import { ShareDialog } from "@/components/documents/ShareDialog";
import { ACCESS_LABELS } from "@/components/documents/values";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, type DocumentDetail } from "@/lib/api";
import { usePermissions } from "@/lib/permissions";
import { useDocument, useDocuments } from "@/lib/queries";

const TABS = ["fields", "assistant", "history"] as const;
type Tab = (typeof TABS)[number];

export function DocumentPage() {
  const { documentId = "" } = useParams();
  const document = useDocument(documentId);

  if (document.isPending) return <Skeleton className="h-64 w-full" />;
  if (document.isError) {
    if (document.error instanceof ApiError && document.error.status === 404) {
      return (
        <EmptyState
          icon={FileQuestion}
          title="Document not found"
          description="It may have been deleted, or it hasn't been shared with you."
        />
      );
    }
    return <QueryError error={document.error} onRetry={() => document.refetch()} />;
  }
  // Keyed by id, so moving between documents (e.g. through a citation) resets the workspace.
  return <Workspace key={document.data.id} document={document.data} />;
}

function Workspace({ document }: { document: DocumentDetail }) {
  const { can } = usePermissions();
  const [params, setParams] = useSearchParams();
  const tab: Tab = TABS.find((name) => name === params.get("tab")) ?? "fields";
  const others = useDocuments();

  const canEdit = document.my_access === "edit" || document.my_access === "owner";
  const canRunAgent = can("agents:run");
  const candidates = (others.data ?? []).filter((candidate) => candidate.id !== document.id);
  const sourceTitles = new Map(others.data?.map((item) => [item.id, item.title]));
  // Runs still in progress when the page loads (e.g. after a reload), so the UI resumes them.
  const activeGenerate = document.active_runs.find((run) => run.run_kind === "generate");
  const activeAssistant = document.active_runs.find((run) => run.run_kind === "assistant_turn");
  const activeEnhance = new Map(
    document.active_runs
      .filter((run) => run.run_kind === "enhance_field" && run.field_path)
      .map((run) => [run.field_path, run.id]),
  );

  return (
    <>
      <PageHeader
        title={document.title}
        description={`${ACCESS_LABELS[document.my_access]} · ${
          document.current_version ? `version ${document.current_version}` : "not generated yet"
        }`}
        actions={
          document.my_access === "owner" && (
            <>
              <ShareDialog documentId={document.id} />
              <DeleteDocumentButton documentId={document.id} title={document.title} />
            </>
          )
        }
      />
      <ProposalsPanel documentId={document.id} canEdit={canEdit} />
      <Tabs
        value={tab}
        onValueChange={(value) => setParams(value === "fields" ? {} : { tab: value })}
      >
        <TabsList>
          <TabsTrigger value="fields">Fields</TabsTrigger>
          <TabsTrigger value="assistant">Assistant</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>
        {/* Kept mounted while hidden, so runs in progress keep their state across tab switches. */}
        <TabsContent value="fields" forceMount className="space-y-4 data-[state=inactive]:hidden">
          {canEdit && canRunAgent && (
            <GeneratePanel
              document={document}
              candidates={candidates}
              initialRunId={activeGenerate?.id}
            />
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {document.fields.map((field) => (
              <FieldCard
                key={field.field_path}
                documentId={document.id}
                field={field}
                canEdit={canEdit}
                canRunAgent={canRunAgent}
                sourceTitles={sourceTitles}
                initialRunId={activeEnhance.get(field.field_path)}
              />
            ))}
          </div>
        </TabsContent>
        <TabsContent value="assistant" forceMount className="data-[state=inactive]:hidden">
          <AssistantPanel
            documentId={document.id}
            canChat={canRunAgent}
            activeRun={activeAssistant}
          />
        </TabsContent>
        <TabsContent value="history">
          <HistoryPanel documentId={document.id} fields={document.fields} />
        </TabsContent>
      </Tabs>
    </>
  );
}
