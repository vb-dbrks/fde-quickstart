import type { Access, FieldSpec } from "@/lib/api";

type FieldType = FieldSpec["type"];

export const ACCESS_LABELS: Record<Access, string> = {
  view: "Can view",
  edit: "Can edit",
  owner: "Owner",
};

/** The value as editable text: list fields have one item per line. */
export function toText(type: FieldType, value: unknown): string {
  if (value === null || value === undefined) return "";
  if (type === "list") return Array.isArray(value) ? value.map(String).join("\n") : String(value);
  return String(value);
}

/** Parse edited text back into the field's shape (the API validates it again). */
export function fromText(type: FieldType, text: string): string | string[] {
  if (type === "list") {
    return text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  }
  return text.trim();
}

export function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (Array.isArray(value)) return value.length === 0;
  return String(value).trim() === "";
}

/** "reading_context" -> "Reading context" */
export function stepLabel(name: string): string {
  const words = name.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
