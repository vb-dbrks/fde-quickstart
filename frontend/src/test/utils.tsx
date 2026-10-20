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
  permissions: ["notes:read"],
};

export const editor: Me = {
  email: "editor@example.com",
  display_name: "Ed Editor",
  roles: ["editor", "viewer"],
  permissions: ["agents:invoke", "notes:read", "notes:write"],
};

export const admin: Me = {
  email: "admin@example.com",
  display_name: "Ada Admin",
  roles: ["admin", "viewer"],
  permissions: ["agents:invoke", "notes:delete_any", "notes:read", "notes:write", "roles:manage"],
};

export const noNotifications: NotificationList = { items: [], unread_count: 0 };

/**
 * Stub fetch. Keys are "METHOD /path" (or just "/path" for GET); values are JSON bodies or Response
 * objects. Unknown paths get a 404.
 */
export function mockApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn(async (request: Request) => {
    const { pathname } = new URL(request.url);
    const handler =
      routes[`${request.method} ${pathname}`] ??
      (request.method === "GET" ? routes[pathname] : undefined);
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
