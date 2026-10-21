import { Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { RunProgress } from "@/components/documents/RunProgress";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { DocumentDetail, DocumentSummary } from "@/lib/api";
import { isTerminal, useAgentRun } from "@/lib/agentRuns";
import { useStartAgentRun } from "@/lib/queries";

/** The API accepts at most this many source documents per run. */
export const MAX_SOURCES = 5;

/**
 * Starts a ``generate`` run: the app sends the agent the document's fields plus the chosen source
 * documents, then polls the run and materialises the fields it returns (with a new version).
 */
export function GeneratePanel({
  document,
  candidates,
  initialRunId,
}: {
  document: DocumentDetail;
  /** Other documents the user can see, offered as sources. */
  candidates: DocumentSummary[];
  initialRunId?: string;
}) {
  const [instruction, setInstruction] = useState("");
  const [sources, setSources] = useState<string[]>([]);
  const [runId, setRunId] = useState(initialRunId);
  const start = useStartAgentRun(document.id);
  const run = useAgentRun(runId, {
    onSettled: (settled) =>
      settled.status === "succeeded"
        ? toast.success("Fields generated")
        : toast.error("Generation failed", { description: settled.error_message ?? undefined }),
  }).data;
  const running = start.isPending || (run !== undefined && !isTerminal(run.status));
  const generated = document.fields.some((field) => field.agent_generates && field.value !== null);

  function toggle(id: string) {
    setSources((current) =>
      current.includes(id) ? current.filter((source) => source !== id) : [...current, id],
    );
  }

  function generate(event: FormEvent) {
    event.preventDefault();
    start.mutate(
      {
        run_kind: "generate",
        instruction: instruction.trim() || null,
        source_document_ids: sources,
      },
      { onSuccess: (started) => setRunId(started.id), onError: (e) => toast.error(e.message) },
    );
  }

  return (
    <Card>
      <form onSubmit={generate} className="contents">
        <CardHeader>
          <CardTitle>
            {generated ? "Regenerate with the agent" : "Generate with the agent"}
          </CardTitle>
          <CardDescription>
            The agent drafts every agent field from this document and the sources you pick. Each run
            creates a new version; edits you make afterwards are kept in the audit trail.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            aria-label="Instructions for the agent"
            placeholder="Optional instructions, e.g. focus on the first month"
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            maxLength={2_000}
            disabled={running}
          />
          {candidates.length > 0 && (
            <fieldset className="space-y-2" disabled={running}>
              <legend className="text-sm font-medium">
                Sources{" "}
                <span className="font-normal text-muted-foreground">
                  ({sources.length}/{MAX_SOURCES})
                </span>
              </legend>
              <div className="flex flex-wrap gap-x-4 gap-y-2">
                {candidates.map((candidate) => {
                  const checked = sources.includes(candidate.id);
                  return (
                    <label key={candidate.id} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="size-4 accent-primary"
                        checked={checked}
                        disabled={!checked && sources.length >= MAX_SOURCES}
                        onChange={() => toggle(candidate.id)}
                      />
                      {candidate.title}
                    </label>
                  );
                })}
              </div>
            </fieldset>
          )}
          {run && <RunProgress run={run} className="rounded-md bg-muted/50 p-3" />}
        </CardContent>
        <CardFooter>
          <Button type="submit" disabled={running}>
            <Sparkles aria-hidden />
            {running ? "Generating…" : generated ? "Regenerate" : "Generate"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
