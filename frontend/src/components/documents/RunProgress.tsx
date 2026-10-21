import { CircleCheck, CircleDashed, CircleX, LoaderCircle } from "lucide-react";

import type { AgentRun } from "@/lib/api";
import { cn } from "@/lib/utils";

import { stepLabel } from "@/components/documents/values";

const STATUS_TEXT: Record<AgentRun["status"], string> = {
  queued: "Queued",
  accepted: "Starting",
  running: "Working",
  succeeded: "Done",
  failed: "Failed",
};

/** The agent's steps (from step_history) as a checklist that updates as the run is polled. */
export function RunProgress({ run, className }: { run: AgentRun; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-live="polite">
      <p className="text-sm font-medium">
        {STATUS_TEXT[run.status]}
        {run.status === "failed" && run.error_code && (
          <span className="font-normal text-muted-foreground"> ({run.error_code})</span>
        )}
      </p>
      {run.step_history.length > 0 && (
        <ol className="space-y-1 text-sm">
          {run.step_history.map((step) => (
            <li key={step.name} className="flex items-center gap-2" data-status={step.status}>
              <StepIcon status={step.status} />
              <span className={cn(step.status === "pending" && "text-muted-foreground")}>
                {stepLabel(step.name)}
              </span>
            </li>
          ))}
        </ol>
      )}
      {run.status === "failed" && run.error_message && (
        <p role="alert" className="text-sm text-destructive">
          {run.error_message}
        </p>
      )}
    </div>
  );
}

function StepIcon({ status }: { status: AgentRun["step_history"][number]["status"] }) {
  const props = { "aria-hidden": true, className: "size-4 shrink-0" } as const;
  switch (status) {
    case "completed":
      return <CircleCheck {...props} className={cn(props.className, "text-emerald-600")} />;
    case "running":
      return <LoaderCircle {...props} className={cn(props.className, "animate-spin")} />;
    case "failed":
      return <CircleX {...props} className={cn(props.className, "text-destructive")} />;
    default:
      return <CircleDashed {...props} className={cn(props.className, "text-muted-foreground")} />;
  }
}
