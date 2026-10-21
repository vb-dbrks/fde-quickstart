import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { completedSteps, field, makeDocument, makeRun, summaryOf } from "@/test/documents";
import { editor, mockApi, noNotifications, renderApp, requestsTo, viewer } from "@/test/utils";

// The first poll of a run happens after RUN_POLL.initialMs (1.5 s).
const POLL = { timeout: 4_000 };

const source = makeDocument({ id: "doc-2", title: "Survey results" });

/** A field's card, named by its label (plus its provenance badge). */
function fieldCard(label: string) {
  return screen.getByRole("group", { name: new RegExp(`^${label}`) });
}

describe("document workspace", () => {
  it("generates fields and shows where they came from", async () => {
    let generated = false;
    const filled = makeDocument({
      current_version: 1,
      fields: [
        field("brief.title", { value: "Onboarding refresh", source: "user" }),
        field("brief.goal", { value: "Reach first value in three days.", source: "user" }),
        field("brief.summary", {
          value: "A drafted summary.",
          source: "agent",
          confidence: "medium",
          confidence_reason: "Drafted from the goal.",
          citations: [{ source_document_id: "doc-2", snippet: "Setup is slow." }],
          agent_run_id: "run-1",
        }),
        field("brief.risks", { value: ["Scope creep"], source: "agent", confidence: "low" }),
      ],
    });
    const fetchMock = mockApi({
      "/api/me": editor,
      "/api/notifications": noNotifications,
      "/api/documents": [summaryOf(makeDocument()), summaryOf(source)],
      "/api/documents/doc-1": () => (generated ? filled : makeDocument()),
      "/api/documents/doc-1/agent-runs": [],
      "POST /api/documents/doc-1/agent-runs": Response.json(makeRun(), { status: 202 }),
      "/api/agent-runs/run-1": () => {
        generated = true;
        return makeRun({ status: "succeeded", step_history: completedSteps });
      },
    });
    const user = userEvent.setup();
    renderApp("/documents/doc-1");

    expect(await screen.findAllByText("Not generated yet.")).toHaveLength(2);
    await user.type(screen.getByLabelText("Instructions for the agent"), "Keep it short");
    await user.click(screen.getByLabelText("Survey results"));
    await user.click(screen.getByRole("button", { name: "Generate" }));

    // Progress comes from step_history.
    expect(await screen.findByText("Reading context")).toBeVisible();
    const [request] = requestsTo(fetchMock, "POST", "/api/documents/doc-1/agent-runs");
    expect(request?.headers.get("Idempotency-Key")).toBeTruthy();
    expect(await request?.json()).toEqual({
      run_kind: "generate",
      instruction: "Keep it short",
      source_document_ids: ["doc-2"],
    });

    expect(await screen.findByText("A drafted summary.", {}, POLL)).toBeVisible();
    const summary = fieldCard("Summary");
    expect(within(summary).getByText(/Agent · medium confidence/)).toBeVisible();
    await user.click(within(summary).getByRole("button", { name: /Why\?/ }));
    expect(await screen.findByRole("link", { name: "Survey results" })).toHaveAttribute(
      "href",
      "/documents/doc-2",
    );
    expect(screen.getByText("Setup is slow.")).toBeVisible();
  });

  it("asks for a revision and records it when accepted", async () => {
    const suggestion = {
      field_path: "brief.summary",
      value: "A shorter summary.",
      confidence: "high",
      confidence_reason: "Clear goal.",
      reasoning: "Trimmed to one sentence.",
      citations: [],
    };
    const fetchMock = mockApi({
      "/api/me": editor,
      "/api/notifications": noNotifications,
      "/api/documents": [summaryOf(makeDocument())],
      "/api/documents/doc-1": makeDocument(),
      "/api/documents/doc-1/agent-runs": [],
      "POST /api/documents/doc-1/agent-runs": Response.json(
        makeRun({ id: "run-2", run_kind: "enhance_field", field_path: "brief.summary" }),
        { status: 202 },
      ),
      "/api/agent-runs/run-2": makeRun({
        id: "run-2",
        run_kind: "enhance_field",
        field_path: "brief.summary",
        status: "succeeded",
        step_history: completedSteps,
        suggestion,
      }),
      "PATCH /api/documents/doc-1/fields/brief.summary": field("brief.summary", {
        value: suggestion.value,
        source: "agent",
      }),
    });
    const user = userEvent.setup();
    renderApp("/documents/doc-1");

    await user.click(await screen.findByRole("button", { name: "Improve Summary with the agent" }));
    await user.type(screen.getByLabelText("How should it change?"), "Shorter");
    await user.click(screen.getByRole("button", { name: /Suggest a revision/ }));

    const review = await screen.findByRole("region", { name: "Suggested revision" }, POLL);
    expect(within(review).getByText("A shorter summary.")).toBeVisible();
    await user.click(within(review).getByRole("button", { name: "Accept" }));

    await waitFor(() =>
      expect(
        requestsTo(fetchMock, "PATCH", "/api/documents/doc-1/fields/brief.summary"),
      ).toHaveLength(1),
    );
    const [patch] = requestsTo(fetchMock, "PATCH", "/api/documents/doc-1/fields/brief.summary");
    expect(await patch?.json()).toEqual({
      value: "A shorter summary.",
      accepted_from_run_id: "run-2",
    });
    const [start] = requestsTo(fetchMock, "POST", "/api/documents/doc-1/agent-runs");
    expect(await start?.json()).toEqual({
      run_kind: "enhance_field",
      field_path: "brief.summary",
      instruction: "Shorter",
    });
  });

  it("is read-only with view access", async () => {
    const shared = makeDocument({ my_access: "view" });
    mockApi({
      "/api/me": editor,
      "/api/notifications": noNotifications,
      "/api/documents": [summaryOf(shared)],
      "/api/documents/doc-1": shared,
    });
    renderApp("/documents/doc-1");

    expect(await screen.findByText("Reach first value in three days.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Generate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Edit / })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Share" })).not.toBeInTheDocument();
  });

  it("hides agent actions from users without agents:run", async () => {
    mockApi({
      "/api/me": viewer,
      "/api/notifications": noNotifications,
      "/api/documents": [],
      "/api/documents/doc-1": makeDocument({ my_access: "edit" }),
    });
    renderApp("/documents/doc-1");

    expect(await screen.findByRole("button", { name: "Edit Goal" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Generate" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Improve Summary with the agent" }),
    ).not.toBeInTheDocument();
  });

  it("explains a missing document", async () => {
    mockApi({ "/api/me": editor, "/api/notifications": noNotifications, "/api/documents": [] });
    renderApp("/documents/nope");

    expect(await screen.findByText("Document not found")).toBeVisible();
  });

  it("chats in a thread the app keeps", async () => {
    let answered = false;
    const thread = {
      id: "thread-1",
      document_id: "doc-1",
      title: "Conversation",
      created_at: "2026-10-21T09:00:00Z",
    };
    const message = (id: number, role: string, content: string) => ({
      id,
      role,
      content,
      citations: [],
      agent_run_id: null,
      created_at: "2026-10-21T09:00:00Z",
    });
    const fetchMock = mockApi({
      "/api/me": editor,
      "/api/notifications": noNotifications,
      "/api/documents": [summaryOf(makeDocument())],
      "/api/documents/doc-1": makeDocument(),
      "/api/documents/doc-1/threads": [],
      "POST /api/documents/doc-1/threads": Response.json(thread, { status: 201 }),
      "/api/threads/thread-1/messages": () =>
        answered
          ? [message(1, "user", "What is the goal?"), message(2, "assistant", "To onboard fast.")]
          : [message(1, "user", "What is the goal?")],
      "POST /api/documents/doc-1/agent-runs": Response.json(
        makeRun({ id: "run-3", run_kind: "assistant_turn", thread_id: "thread-1" }),
        { status: 202 },
      ),
      "/api/agent-runs/run-3": () => {
        answered = true;
        return makeRun({
          id: "run-3",
          run_kind: "assistant_turn",
          thread_id: "thread-1",
          status: "succeeded",
          step_history: completedSteps,
          answer: "To onboard fast.",
        });
      },
    });
    const user = userEvent.setup();
    renderApp("/documents/doc-1?tab=assistant");

    await user.type(await screen.findByLabelText("Message"), "What is the goal?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("To onboard fast.", {}, POLL)).toBeVisible();
    const [start] = requestsTo(fetchMock, "POST", "/api/documents/doc-1/agent-runs");
    expect(await start?.json()).toEqual({
      run_kind: "assistant_turn",
      thread_id: "thread-1",
      message: "What is the goal?",
    });
  });
});
