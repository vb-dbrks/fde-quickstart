import type {
  AgentRun,
  DocumentDetail,
  DocumentField,
  DocumentSummary,
  DocumentType,
} from "@/lib/api";

const NOW = "2026-10-21T09:00:00Z";

export const briefType: DocumentType = {
  name: "brief",
  label: "Brief",
  description: "A short working brief.",
  fields: [
    {
      field_path: "brief.title",
      label: "Title",
      type: "text",
      agent_generates: false,
      required: true,
      description: "A short name.",
    },
    {
      field_path: "brief.goal",
      label: "Goal",
      type: "text",
      agent_generates: false,
      required: true,
      description: "What it should achieve.",
    },
    {
      field_path: "brief.summary",
      label: "Summary",
      type: "text",
      agent_generates: true,
      required: false,
      description: "Two to four sentences.",
    },
    {
      field_path: "brief.risks",
      label: "Risks",
      type: "list",
      agent_generates: true,
      required: false,
      description: "What could go wrong.",
    },
  ],
};

export function field(path: string, overrides: Partial<DocumentField> = {}): DocumentField {
  const spec = briefType.fields.find((candidate) => candidate.field_path === path);
  if (!spec) throw new Error(`unknown field ${path}`);
  return {
    field_path: spec.field_path,
    label: spec.label,
    type: spec.type,
    agent_generates: spec.agent_generates,
    value: null,
    source: null,
    confidence: null,
    confidence_reason: null,
    reasoning: null,
    citations: [],
    agent_run_id: null,
    updated_by: null,
    updated_at: null,
    ...overrides,
  };
}

export function makeDocument(overrides: Partial<DocumentDetail> = {}): DocumentDetail {
  return {
    id: "doc-1",
    document_type: "brief",
    title: "Onboarding refresh",
    my_access: "owner",
    current_version: 0,
    created_by: "editor@example.com",
    updated_at: NOW,
    fields: [
      field("brief.title", { value: "Onboarding refresh", source: "user" }),
      field("brief.goal", { value: "Reach first value in three days.", source: "user" }),
      field("brief.summary"),
      field("brief.risks"),
    ],
    active_runs: [],
    ...overrides,
  };
}

export function summaryOf(document: DocumentDetail): DocumentSummary {
  return {
    id: document.id,
    document_type: document.document_type,
    title: document.title,
    my_access: document.my_access,
    current_version: document.current_version,
    created_by: document.created_by,
    updated_at: document.updated_at,
  };
}

export function makeRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "run-1",
    document_id: "doc-1",
    thread_id: null,
    run_kind: "generate",
    field_path: null,
    status: "accepted",
    step_history: [
      { name: "reading_context", status: "pending", started_at: null, completed_at: null },
      { name: "drafting_fields", status: "pending", started_at: null, completed_at: null },
    ],
    suggestion: null,
    answer: null,
    error_code: null,
    error_message: null,
    trace_id: null,
    created_at: NOW,
    completed_at: null,
    ...overrides,
  };
}

export const completedSteps: AgentRun["step_history"] = [
  { name: "reading_context", status: "completed", started_at: NOW, completed_at: NOW },
  { name: "drafting_fields", status: "completed", started_at: NOW, completed_at: NOW },
];
