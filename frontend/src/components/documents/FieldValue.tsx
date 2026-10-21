import type { FieldSpec } from "@/lib/api";

import { isEmpty } from "@/components/documents/values";

/** Read-only rendering of a field value: a paragraph for text, a bulleted list for lists. */
export function FieldValue({
  type,
  value,
  placeholder,
}: {
  type: FieldSpec["type"];
  value: unknown;
  placeholder?: string;
}) {
  if (isEmpty(value)) {
    return <p className="text-sm text-muted-foreground italic">{placeholder ?? "Empty"}</p>;
  }
  if (type === "list" && Array.isArray(value)) {
    return (
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {value.map((item, index) => (
          <li key={index}>{String(item)}</li>
        ))}
      </ul>
    );
  }
  return <p className="text-sm whitespace-pre-wrap">{String(value)}</p>;
}
