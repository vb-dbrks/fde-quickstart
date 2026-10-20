import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Placeholder for empty lists, missing access or unconfigured features. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  tone = "default",
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  tone?: "default" | "error";
}) {
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      className="flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-12 text-center"
    >
      <Icon
        aria-hidden
        className={cn("size-8", tone === "error" ? "text-destructive" : "text-muted-foreground")}
      />
      <div className="space-y-1">
        <p className="font-medium">{title}</p>
        {description && <div className="max-w-md text-sm text-muted-foreground">{description}</div>}
      </div>
      {action}
    </div>
  );
}
