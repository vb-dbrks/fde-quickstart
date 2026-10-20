import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { editor, mockApi, noNotifications, renderApp, requestsTo, viewer } from "@/test/utils";

describe("notes page", () => {
  it("is read-only for viewers", async () => {
    mockApi({ "/api/me": viewer, "/api/notifications": noNotifications, "/api/notes": [] });
    renderApp("/notes");

    expect(await screen.findByText(/read-only access/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add note" })).not.toBeInTheDocument();
    expect(await screen.findByText("No notes yet")).toBeVisible();
  });

  it("lets editors add notes", async () => {
    const created = {
      id: 1,
      title: "Kick-off",
      body: "",
      owner: editor.email,
      created_at: new Date().toISOString(),
      can_delete: true,
    };
    const fetchMock = mockApi({
      "/api/me": editor,
      "/api/notifications": noNotifications,
      "/api/notes": [],
      "POST /api/notes": Response.json(created, { status: 201 }),
    });
    const user = userEvent.setup();
    renderApp("/notes");

    await user.type(await screen.findByLabelText("Title"), "Kick-off");
    await user.click(screen.getByRole("button", { name: "Add note" }));

    await waitFor(() => expect(requestsTo(fetchMock, "POST", "/api/notes")).toHaveLength(1));
    const [request] = requestsTo(fetchMock, "POST", "/api/notes");
    expect(await request?.json()).toEqual({ title: "Kick-off", body: "" });
  });
});
