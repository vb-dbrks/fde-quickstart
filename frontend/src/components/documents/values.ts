import type { Access, FeedbackReason, FieldSpec } from "@/lib/api";

type FieldType = FieldSpec["type"];

export const ACCESS_LABELS: Record<Access, string> = {
  view: "Can view",
  edit: "Can edit",
  owner: "Owner",
};

/** Reasons a user can give with a rating (the agent contract's feedback vocabulary). */
export const GOOD_REASONS: Partial<Record<FeedbackReason, string>> = {
  accurate: "Accurate",
  usable_as_is: "Usable as is",
};
export const BAD_REASONS: Partial<Record<FeedbackReason, string>> = {
  factually_incorrect: "Factually incorrect",
  unsupported_by_sources: "Not supported by the sources",
  missing_detail: "Missing detail",
  too_long: "Too long",
  wrong_tone: "Wrong tone or style",
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
