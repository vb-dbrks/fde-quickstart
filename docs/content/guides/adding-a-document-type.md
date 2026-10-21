---
title: Adding a document type or field
---

# Adding a document type or field

Document types and their fields are defined in one file: `contracts/field-catalog.yaml`. The API, the
UI and both agent runners read it. Start there.

```yaml
document_types:
  brief:
    label: Brief
    description: A short working brief. ...
    fields:
      brief.title:
        label: Title
        type: text           # text (a string) or list (a list of strings)
        agent_generates: false
        required: true
        description: A short name for the piece of work.
      brief.summary:
        label: Summary
        type: text
        agent_generates: true
        description: Two to four sentences restating the goal and the approach in plain language.
```

The loader (`backend/contracts/field_catalog.py`) enforces a few rules when the app starts:

- every field path starts with its document type's name and a dot (`brief.`);
- every document type has a `<type>.title` field, which becomes the document's title;
- `type` is `text` or `list`, and `agent_generates` is set on every field.

## Adding a field

Add it to the catalog. Then, with no code changes:

- `GET /api/document-types` lists it, and the UI shows it: in the **New** dialog if users enter it, as a
  card on the document page, with **Generate** and **Improve** for agent fields.
- The real runners include its label and description in the prompt, and the structured output asks
  for it; the fake runner drafts it.
- The output checks accept it, materialisation writes it, versions and the audit trail include it.
- No migration: values are stored one row per field in `document_fields`.

Existing documents have no value for the new field until someone enters it or the agent generates it.

Changing a field's description changes what the real agent writes. Run `make eval` before and after.

## Adding a document type

Add it to the catalog with its fields, including `<type>.title`. The documents page shows a **New**
button per type. The real runners use the type's label and description in the prompt.

Consider a prompt change if the generic instructions in `backend/agents/prompts/generate.md` don't fit
the new type, and add eval rows for it to `evals/dataset.jsonl`.

## What needs code

- A new field type (a number, a date, a nested structure): `FieldSpec.coerce` and the type checks in
  `backend/contracts/field_catalog.py`, the `type` literals in `backend/domain/schemas.py`, the model
  output schemas in `backend/agents/runners/`, the fake runner, and the UI
  (`frontend/src/components/documents/FieldValue.tsx` and `values.ts`).
- Removing or renaming a field: stored rows keep the old path. Migrate them with a data migration, or
  leave them; fields that are no longer in the catalog are not shown.
- Rules between fields, or per-type permissions: services and `backend/auth/`.
