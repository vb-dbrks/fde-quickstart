import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { vi } from "vitest";

import type { Me, NotificationList } from "@/lib/api";
import { routes } from "@/routes";

export const viewer: Me = {
  email: "viewer@example.com",
  display_name: "Vera Viewer",
  roles: ["viewer"],
  permissions: [],
};

export const editor: Me = {
  email: "editor@example.com",
  display_name: "Ed Editor",
  roles: ["editor", "viewer"],
  permissions: ["agents:run", "documents:create"],
};

export const admin: Me = {
  email: "admin@example.com",
  display_name: "Ada Admin",
  roles: ["admin", "viewer"],
  permissions: ["agents:run", "documents:access_any", "documents:create", "roles:manage"],
};

export const noNotifications: NotificationList = { items: [], unread_count: 0 };

type Handler = unknown | ((request: Request) => unknown);

/**
 * Stub fetch. Keys are "METHOD /path" (or just "/path" for GET); values are JSON bodies, Response
 * objects, or functions of the request returning either (for responses that change over time).
 * Unknown paths get a 404.
 */
export function mockApi(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(async (request: Request) => {
    const { pathname } = new URL(request.url);
    const route =
      routes[`${request.method} ${pathname}`] ??
      (request.method === "GET" ? routes[pathname] : undefined) ??
      (pathname === "/api/examples" ? ["chat", "generation", "documents"] : undefined);
    const handler = typeof route === "function" ? await route(request) : route;
    if (handler === undefined) return Response.json({ detail: "Not Found" }, { status: 404 });
    return handler instanceof Response ? handler.clone() : Response.json(handler);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function requestsTo(fetchMock: ReturnType<typeof mockApi>, method: string, path: string) {
  return fetchMock.mock.calls
    .map(([request]) => request)
    .filter((request) => request.method === method && new URL(request.url).pathname === path);
}

export function renderApp(path = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}
