import createClient from "openapi-fetch";

import type { components, paths } from "@/api/schema";

type Schemas = components["schemas"];
export type Me = Schemas["MeOut"];
export type Health = Schemas["HealthOut"];
export type Role = Schemas["Role"];
export type Permission = Schemas["Permission"];
export type RoleInfo = Schemas["RoleInfo"];
export type RoleAssignment = Schemas["RoleAssignmentOut"];
export type Notification = Schemas["NotificationOut"];
export type NotificationList = Schemas["NotificationList"];

export type Access = Schemas["Access"];
export type DocumentType = Schemas["DocumentTypeOut"];
export type FieldSpec = Schemas["FieldSpecOut"];
export type DocumentSummary = Schemas["DocumentSummary"];
export type DocumentDetail = Schemas["DocumentOut"];
export type DocumentField = Schemas["FieldOut"];
export type Citation = Schemas["CitationOut"];
export type DocumentVersion = Schemas["VersionOut"];
export type AuditEntry = Schemas["AuditOut"];
export type AccessEntry = Schemas["AccessOut"];

export type AgentRun = Schemas["AgentRunOut"];
export type AgentRunCreate = Schemas["AgentRunCreate"];
export type AgentRunKind = AgentRunCreate["run_kind"];
export type RunStatus = Schemas["RunStatus"];
export type Suggestion = Schemas["SuggestionOut"];
export type Thread = Schemas["ThreadOut"];
export type Message = Schemas["MessageOut"];
export type RatingIn = Schemas["RatingIn"];
export type Rating = Schemas["RatingOut"];
export type FeedbackReason = Rating["reasons"][number];

/**
 * Typed client for the FastAPI backend. Paths and payloads come from its OpenAPI schema;
 * run `make api-types` after changing backend/domain/schemas.py or the routes.
 */
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  // Look fetch up per request, so tests can stub it.
  fetch: (request) => globalThis.fetch(request),
});

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/** Return the response body, or throw an ApiError carrying FastAPI's error detail. */
export async function unwrap<T>(request: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok) {
    throw new ApiError(response.status, describeError(error, response));
  }
  return data as T;
}

function describeError(error: unknown, response: Response): string {
  if (error && typeof error === "object" && "detail" in error) {
    const { detail } = error;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((item: { msg?: string }) => item.msg ?? String(item)).join("; ");
    }
  }
  return `${response.status} ${response.statusText}`.trim();
}

/**
 * A request body plus the Idempotency-Key for one user action. Create it once, when the user acts,
 * and pass it as the mutation's variables: TanStack Query hands the same variables to every retry,
 * so a retry after a dropped connection sends the same key and the server runs the action once.
 */
export type Keyed<T> = { body: T; key: string };

export function keyed<T>(body: T): Keyed<T> {
  return { body, key: crypto.randomUUID() };
}

/**
 * Mutation retry policy: retry only when the request may never have reached the server (a network
 * error), and only twice. An ApiError means the server answered, so repeating would not help.
 */
export function retryNetworkErrors(failureCount: number, error: Error): boolean {
  return failureCount < 2 && !(error instanceof ApiError);
}

export const RETRY_DELAY_MS = 500;
