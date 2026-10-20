import createClient from "openapi-fetch";

import type { components, paths } from "@/api/schema";

type Schemas = components["schemas"];
export type Me = Schemas["MeOut"];
export type Note = Schemas["NoteOut"];
export type NoteIn = Schemas["NoteIn"];
export type Notification = Schemas["NotificationOut"];
export type NotificationList = Schemas["NotificationList"];
export type Role = Schemas["Role"];
export type Permission = Schemas["Permission"];
export type RoleInfo = Schemas["RoleInfo"];
export type RoleAssignment = Schemas["RoleAssignmentOut"];
export type AgentInfo = Schemas["AgentInfo"];
export type Health = Schemas["HealthOut"];

/**
 * Typed client for the FastAPI backend. Paths and payloads come from its OpenAPI schema;
 * run `make api-types` after changing backend/app/schemas.py or the routes.
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
