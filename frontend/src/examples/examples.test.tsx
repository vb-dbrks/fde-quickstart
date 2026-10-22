import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { editor, mockApi, noNotifications, renderApp, requestsTo } from "@/test/utils";

it("generates, edits and accepts independently of the document workspace", async () => {
  const value = { title: "AG-UI", summary: "A draft", key_points: ["Events"] };
  let status = "pending";
  const fetcher = mockApi({
    "/api/me": editor,
    "/api/notifications": noNotifications,
    "/api/examples": ["generation"],
    "/api/runs": [],
    "POST /api/runs": { id: "r", status: "accepted" },
    "/api/runs/r/events": new Response(
      [
        { type: "RUN_STARTED", runId: "r", threadId: "r" },
        { type: "STATE_SNAPSHOT", snapshot: { result: value, provisional: false } },
        { type: "RUN_FINISHED", runId: "r", threadId: "r" },
      ]
        .map((event, i) => `data: ${JSON.stringify({ sequence: i + 1, event })}\n\n`)
        .join(""),
    ),
    "/api/runs/r/review": () => ({ status, value }),
    "POST /api/runs/r/review": () => {
      status = "accepted";
      return { status, value };
    },
  });
  renderApp("/generation");
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Topic"), "AG-UI");
  await user.click(screen.getByRole("button", { name: "Generate draft" }));
  expect(await screen.findByRole("region", { name: "Review generated content" })).toBeVisible();
  expect(requestsTo(fetcher, "POST", "/api/runs/r/review")).toHaveLength(0);
  await user.click(screen.getByText("Edit before accepting"));
  await user.clear(screen.getByLabelText("Edit Review generated content"));
  await user.paste(JSON.stringify({ ...value, title: "Edited title" }));
  await user.click(screen.getByRole("button", { name: "Accept" }));
  expect(await screen.findByText("Saved result")).toBeVisible();
  const [accepted] = requestsTo(fetcher, "POST", "/api/runs/r/review");
  expect(await accepted?.json()).toEqual({
    decision: "accepted",
    value: { ...value, title: "Edited title" },
  });
  expect(fetcher.mock.calls.some(([request]) => /documents|field-catalog/.test(request.url))).toBe(
    false,
  );
});

it("gates disabled example routes and leaves chat available", async () => {
  const fetcher = mockApi({
    "/api/me": editor,
    "/api/notifications": noNotifications,
    "/api/examples": ["chat"],
  });
  renderApp("/generation");
  expect(await screen.findByText("This example is not enabled.")).toBeVisible();
  expect(await screen.findByRole("link", { name: "Chat" })).toBeVisible();
  expect(screen.queryByRole("link", { name: "Generation" })).not.toBeInTheDocument();
  expect(requestsTo(fetcher, "GET", "/api/runs")).toHaveLength(0);
});
