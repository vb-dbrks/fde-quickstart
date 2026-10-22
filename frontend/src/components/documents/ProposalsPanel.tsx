import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { request, post } from "@/agent/transport";
import { ReviewCard, Citations } from "@/agent/components";
import { Button } from "@/components/ui/button";

type Proposal = {
  run_id: string;
  field_path: string;
  before: unknown;
  output: { value: unknown; citations?: { source_document_id: string; snippet?: string }[] };
  status: string;
};
export function ProposalsPanel({ documentId, canEdit }: { documentId: string; canEdit: boolean }) {
  const cache = useQueryClient();
  const [error, setError] = useState("");
  const proposals = useQuery({
    queryKey: ["document-proposals", documentId],
    queryFn: () => request<Proposal[]>(`/documents/${documentId}/proposals`),
  });
  async function review(runId: string, accept: Record<string, unknown>, reject: string[]) {
    await post(`/documents/${documentId}/proposals/${runId}/review`, { accept, reject });
    await cache.invalidateQueries({ queryKey: ["document-proposals", documentId] });
    await cache.invalidateQueries({ predicate: (q) => q.queryKey.includes(documentId) });
  }
  const groups = new Map<string, Proposal[]>();
  for (const proposal of proposals.data ?? [])
    groups.set(proposal.run_id, [...(groups.get(proposal.run_id) ?? []), proposal]);
  return (
    <div className="space-y-5">
      {[...groups].map(([runId, items]) => (
        <section key={runId} className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-medium">Draft ready for review</h2>
            <Button
              variant="outline"
              disabled={!canEdit}
              onClick={() => {
                setError("");
                void review(
                  runId,
                  Object.fromEntries(items.map((p) => [p.field_path, p.output.value])),
                  [],
                ).catch((e: Error) => setError(e.message));
              }}
            >
              Accept all remaining fields
            </Button>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {items.map((p) => (
              <div key={p.field_path}>
                <ReviewCard
                  title={p.field_path.split(".").at(-1)?.replaceAll("_", " ") ?? p.field_path}
                  before={p.before}
                  value={p.output.value}
                  disabled={!canEdit}
                  accept={(value) => review(runId, { [p.field_path]: value }, [])}
                  reject={() => review(runId, {}, [p.field_path])}
                />
                <Citations
                  items={(p.output.citations ?? []).map((c, index) => ({
                    id: `${c.source_document_id}:${index}`,
                    href: `/documents/${c.source_document_id}`,
                    label: c.snippet || "View source",
                  }))}
                />
              </div>
            ))}
          </div>
        </section>
      ))}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
