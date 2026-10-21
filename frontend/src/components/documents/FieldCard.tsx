import { Check, Pencil, Sparkles, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { FieldValue } from "@/components/documents/FieldValue";
import { ProvenanceBadge, ProvenanceDetails } from "@/components/documents/Provenance";
import { RunProgress } from "@/components/documents/RunProgress";
import { fromText, toText } from "@/components/documents/values";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { AgentRun, DocumentField } from "@/lib/api";
import { isTerminal, useAgentRun } from "@/lib/agentRuns";
import { useStartAgentRun, useUpdateField } from "@/lib/queries";

type Mode = "view" | "edit" | "enhance";

/**
 * One field of a document. People can edit it; for agent fields an editor can also ask the agent
 * for a revision (an ``enhance_field`` run). The suggestion only replaces the value once accepted.
 */
export function FieldCard({
  documentId,
  field,
  canEdit,
  canRunAgent,
  sourceTitles,
  initialRunId,
}: {
  documentId: string;
  field: DocumentField;
  canEdit: boolean;
  canRunAgent: boolean;
  sourceTitles: Map<string, string>;
  /** An enhance run still in progress (after a reload). */
  initialRunId?: string;
}) {
  const [mode, setMode] = useState<Mode>(initialRunId ? "enhance" : "view");
  const [runId, setRunId] = useState<string | undefined>(initialRunId);
  const canEnhance = canEdit && canRunAgent && field.agent_generates;

  return (
    <Card className="gap-3" role="group" aria-labelledby={`field-${field.field_path}`}>
      <CardHeader>
        <CardTitle id={`field-${field.field_path}`} className="flex flex-wrap items-center gap-2">
          {field.label}
          <ProvenanceBadge field={field} />
        </CardTitle>
        <CardAction className="flex items-center gap-1">
          <ProvenanceDetails field={field} sourceTitles={sourceTitles} />
          {canEdit && mode === "view" && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2"
              aria-label={`Edit ${field.label}`}
              onClick={() => setMode("edit")}
            >
              <Pencil aria-hidden />
            </Button>
          )}
          {canEnhance && mode === "view" && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2"
              aria-label={`Improve ${field.label} with the agent`}
              onClick={() => setMode("enhance")}
            >
              <Sparkles aria-hidden />
            </Button>
          )}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        {mode === "edit" ? (
          <EditField documentId={documentId} field={field} onDone={() => setMode("view")} />
        ) : (
          <FieldValue
            type={field.type}
            value={field.value}
            placeholder={field.agent_generates ? "Not generated yet." : "Not filled in yet."}
          />
        )}
        {mode === "enhance" && (
          <EnhanceField
            documentId={documentId}
            field={field}
            runId={runId}
            onStarted={setRunId}
            onDone={() => {
              setRunId(undefined);
              setMode("view");
            }}
          />
        )}
      </CardContent>
    </Card>
  );
}

function EditField({
  documentId,
  field,
  onDone,
}: {
  documentId: string;
  field: DocumentField;
  onDone: () => void;
}) {
  const [text, setText] = useState(toText(field.type, field.value));
  const update = useUpdateField(documentId);

  function save(event: FormEvent) {
    event.preventDefault();
    update.mutate(
      { fieldPath: field.field_path, value: fromText(field.type, text) },
      {
        onSuccess: () => {
          toast.success(`${field.label} saved`);
          onDone();
        },
        onError: (error) => toast.error(error.message),
      },
    );
  }

  return (
    <form onSubmit={save} className="space-y-2">
      <Textarea
        aria-label={field.label}
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={field.type === "list" ? 5 : 3}
        autoFocus
      />
      {field.type === "list" && <p className="text-xs text-muted-foreground">One item per line.</p>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={update.isPending}>
          {update.isPending ? "Saving…" : "Save"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function EnhanceField({
  documentId,
  field,
  runId,
  onStarted,
  onDone,
}: {
  documentId: string;
  field: DocumentField;
  runId: string | undefined;
  onStarted: (runId: string) => void;
  onDone: () => void;
}) {
  const [instruction, setInstruction] = useState("");
  const start = useStartAgentRun(documentId);
  const run = useAgentRun(runId, {
    onSettled: (settled) => {
      if (settled.status === "failed") toast.error(`Couldn't improve ${field.label}`);
    },
  }).data;

  function suggest(event: FormEvent) {
    event.preventDefault();
    start.mutate(
      {
        run_kind: "enhance_field",
        field_path: field.field_path,
        instruction: instruction.trim() || null,
      },
      { onSuccess: (started) => onStarted(started.id), onError: (e) => toast.error(e.message) },
    );
  }

  if (run?.status === "succeeded" && run.suggestion) {
    return <SuggestionReview documentId={documentId} field={field} run={run} onDone={onDone} />;
  }
  if (run && !isTerminal(run.status)) {
    return <RunProgress run={run} className="rounded-md bg-muted/50 p-3" />;
  }

  return (
    <form onSubmit={suggest} className="space-y-2 rounded-md bg-muted/50 p-3">
      {run?.status === "failed" && <RunProgress run={run} />}
      <Input
        aria-label="How should it change?"
        placeholder="How should it change? e.g. shorter, more specific, add owners"
        value={instruction}
        onChange={(event) => setInstruction(event.target.value)}
        maxLength={2_000}
        autoFocus
      />
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={start.isPending}>
          <Sparkles aria-hidden /> {start.isPending ? "Asking…" : "Suggest a revision"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function SuggestionReview({
  documentId,
  field,
  run,
  onDone,
}: {
  documentId: string;
  field: DocumentField;
  run: AgentRun;
  onDone: () => void;
}) {
  const update = useUpdateField(documentId);
  const suggestion = run.suggestion;
  if (!suggestion) return null;

  function accept() {
    update.mutate(
      { fieldPath: field.field_path, value: suggestion?.value, acceptedFromRunId: run.id },
      {
        onSuccess: () => {
          toast.success(`${field.label} updated`);
          onDone();
        },
        onError: (error) => toast.error(error.message),
      },
    );
  }

  return (
    <section
      aria-label="Suggested revision"
      className="space-y-2 rounded-md border border-dashed border-primary/40 bg-primary/5 p-3"
    >
      <p className="text-xs font-medium text-muted-foreground uppercase">
        Suggestion · {suggestion.confidence} confidence
      </p>
      <FieldValue type={field.type} value={suggestion.value} />
      {suggestion.reasoning && (
        <p className="text-xs text-muted-foreground">{suggestion.reasoning}</p>
      )}
      <div className="flex gap-2">
        <Button size="sm" onClick={accept} disabled={update.isPending}>
          <Check aria-hidden /> Accept
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          <X aria-hidden /> Dismiss
        </Button>
      </div>
    </section>
  );
}
