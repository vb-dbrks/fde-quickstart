import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { admin, mockApi, noNotifications, renderApp, viewer } from "@/test/utils";

const health = { status: "ok", database: "ok" };

describe("app shell", () => {
  it("hides admin navigation from viewers", async () => {
    mockApi({ "/api/me": viewer, "/api/notifications": noNotifications, "/api/health": health });
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Welcome, Vera Viewer" })).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Notes" })).toBeVisible();
    expect(within(nav).queryByRole("link", { name: "Users & roles" })).not.toBeInTheDocument();
  });

  it("shows admin navigation to admins", async () => {
    mockApi({ "/api/me": admin, "/api/notifications": noNotifications, "/api/health": health });
    renderApp("/");

    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(await within(nav).findByRole("link", { name: "Users & roles" })).toBeVisible();
  });

  it("blocks the admin page for viewers", async () => {
    mockApi({ "/api/me": viewer, "/api/notifications": noNotifications });
    renderApp("/admin/roles");

    expect(await screen.findByText("You don't have access to this page")).toBeVisible();
  });

  it("shows a not-found page for unknown routes", async () => {
    mockApi({ "/api/me": viewer, "/api/notifications": noNotifications });
    renderApp("/does-not-exist");

    expect(await screen.findByText("Page not found")).toBeVisible();
  });
});
