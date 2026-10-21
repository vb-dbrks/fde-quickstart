import { Info, Sparkles, UserPen } from "lucide-react";
import { Link } from "react-router";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { Citation } from "@/lib/api";

type Provenance = {
  source?: "user" | "agent" | null;
  confidence?: string | null;
  confidence_reason?: string | null;
  reasoning?: string | null;
  citations?: Citation[];
};

/** Where a field's value came from: the agent (with its confidence) or a person. */
export function ProvenanceBadge({ field }: { field: Provenance }) {
  if (field.source === "agent") {
    return (
      <Badge variant="secondary">
        <Sparkles aria-hidden /> Agent{field.confidence ? ` · ${field.confidence} confidence` : ""}
      </Badge>
    );
  }
  if (field.source === "user") {
    return (
      <Badge variant="outline">
        <UserPen aria-hidden /> User
      </Badge>
    );
  }
  return null;
}

/** The agent's reasoning and the sources it cited, behind a small "Why?" button. */
export function ProvenanceDetails({
  field,
  sourceTitles,
}: {
  field: Provenance;
  sourceTitles: Map<string, string>;
}) {
  if (field.source !== "agent") return null;
  const citations = field.citations ?? [];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs">
          <Info aria-hidden /> Why?
          {citations.length > 0 &&
            ` · ${citations.length} source${citations.length === 1 ? "" : "s"}`}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-3 text-sm">
        {field.confidence_reason && (
          <section>
            <h4 className="font-medium">Confidence: {field.confidence}</h4>
            <p className="text-muted-foreground">{field.confidence_reason}</p>
          </section>
        )}
        {field.reasoning && (
          <section>
            <h4 className="font-medium">Reasoning</h4>
            <p className="text-muted-foreground">{field.reasoning}</p>
          </section>
        )}
        <section>
          <h4 className="font-medium">Sources</h4>
          {citations.length === 0 ? (
            <p className="text-muted-foreground">No sources cited.</p>
          ) : (
            <ul className="space-y-2">
              {citations.map((citation, index) => (
                <li key={index}>
                  <Link
                    to={`/documents/${citation.source_document_id}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    {sourceTitles.get(citation.source_document_id) ?? "Source document"}
                  </Link>
                  {citation.snippet && (
                    <blockquote className="mt-1 border-l-2 pl-2 text-muted-foreground">
                      {citation.snippet}
                    </blockquote>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </PopoverContent>
    </Popover>
  );
}
