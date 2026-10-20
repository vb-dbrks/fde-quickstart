import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderApp, requestsTo, viewer } from "@/test/utils";

describe("notification bell", () => {
  it("shows the unread count and marks everything read", async () => {
    const fetchMock = mockApi({
      "/api/me": viewer,
      "/api/health": { status: "ok", database: "ok" },
      "/api/notifications": {
        unread_count: 1,
        items: [
          {
            id: 1,
            kind: "role_granted",
            title: "You now have the editor role",
            body: "Granted by admin@example.com.",
            link: "/",
            created_at: new Date().toISOString(),
            read_at: null,
          },
        ],
      },
      "POST /api/notifications/read-all": { updated: 1 },
    });
    const user = userEvent.setup();
    renderApp("/");

    await user.click(await screen.findByRole("button", { name: "Notifications (1 unread)" }));
    expect(await screen.findByText("You now have the editor role")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Mark all as read" }));
    await waitFor(() =>
      expect(requestsTo(fetchMock, "POST", "/api/notifications/read-all")).toHaveLength(1),
    );
  });
});
