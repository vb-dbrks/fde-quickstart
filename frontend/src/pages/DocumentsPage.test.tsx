import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { DocumentType } from "@/lib/api";
import { briefType, makeDocument, summaryOf } from "@/test/documents";
import { editor, mockApi, noNotifications, renderApp, requestsTo, viewer } from "@/test/utils";

const common = { "/api/notifications": noNotifications, "/api/document-types": [briefType] };

describe("documents page", () => {
  it("lists documents with the user's access", async () => {
    const shared = makeDocument({ id: "doc-2", title: "Shared plan", my_access: "view" });
    mockApi({ ...common, "/api/me": viewer, "/api/documents": [summaryOf(shared)] });
    renderApp("/documents");

    const link = await screen.findByRole("link", { name: "Shared plan" });
    expect(link).toHaveAttribute("href", "/documents/doc-2");
    expect(screen.getByText("Can view")).toBeVisible();
    expect(screen.queryByRole("button", { name: "New brief" })).not.toBeInTheDocument();
  });

  it("lets editors create a document from the catalog's user fields", async () => {
    const created = makeDocument({ title: "Kick-off" });
    const fetchMock = mockApi({
      ...common,
      "/api/me": editor,
      "/api/documents": [],
      "POST /api/documents": Response.json(created, { status: 201 }),
      "/api/documents/doc-1": created,
    });
    const user = userEvent.setup();
    renderApp("/documents");

    await user.click(await screen.findByRole("button", { name: "New brief" }));
    // Agent fields are not asked for.
    expect(screen.queryByLabelText("Summary")).not.toBeInTheDocument();
    const create = screen.getByRole("button", { name: "Create" });
    expect(create).toBeDisabled();
    await user.type(screen.getByLabelText("Title"), "Kick-off");
    await user.type(screen.getByLabelText("Goal"), "Agree the plan");
    await user.click(create);

    await waitFor(() => expect(requestsTo(fetchMock, "POST", "/api/documents")).toHaveLength(1));
    const [request] = requestsTo(fetchMock, "POST", "/api/documents");
    expect(request?.headers.get("Idempotency-Key")).toBeTruthy();
    expect(await request?.json()).toEqual({
      document_type: "brief",
      fields: { "brief.title": "Kick-off", "brief.goal": "Agree the plan" },
    });
    expect(await screen.findByRole("heading", { name: "Kick-off" })).toBeVisible();
  });

  it("sends list fields as lists, one item per line", async () => {
    const withList: DocumentType = {
      ...briefType,
      fields: [
        ...briefType.fields,
        {
          field_path: "brief.stakeholders",
          label: "Stakeholders",
          type: "list",
          agent_generates: false,
          required: false,
          description: "Who cares about this.",
        },
      ],
    };
    const fetchMock = mockApi({
      ...common,
      "/api/document-types": [withList],
      "/api/me": editor,
      "/api/documents": [],
      "POST /api/documents": Response.json(makeDocument(), { status: 201 }),
      "/api/documents/doc-1": makeDocument(),
    });
    const user = userEvent.setup();
    renderApp("/documents");

    await user.click(await screen.findByRole("button", { name: "New brief" }));
    await user.type(screen.getByLabelText("Title"), "Kick-off");
    await user.type(screen.getByLabelText("Goal"), "Agree the plan");
    await user.type(screen.getByLabelText("Stakeholders"), "Product{Enter} {Enter}Support");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(requestsTo(fetchMock, "POST", "/api/documents")).toHaveLength(1));
    const [request] = requestsTo(fetchMock, "POST", "/api/documents");
    const body = (await request?.json()) as { fields: Record<string, unknown> };
    expect(body.fields["brief.stakeholders"]).toEqual(["Product", "Support"]);
  });

  it("retries a dropped request with the same Idempotency-Key", async () => {
    let attempts = 0;
    const fetchMock = mockApi({
      ...common,
      "/api/me": editor,
      "/api/documents": [],
      "POST /api/documents": () => {
        if (++attempts === 1) throw new TypeError("Failed to fetch"); // the connection dropped
        return Response.json(makeDocument(), { status: 201 });
      },
      "/api/documents/doc-1": makeDocument(),
    });
    const user = userEvent.setup();
    renderApp("/documents");

    await user.click(await screen.findByRole("button", { name: "New brief" }));
    await user.type(screen.getByLabelText("Title"), "Kick-off");
    await user.type(screen.getByLabelText("Goal"), "Agree the plan");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(requestsTo(fetchMock, "POST", "/api/documents")).toHaveLength(2));
    const keys = requestsTo(fetchMock, "POST", "/api/documents").map((r) =>
      r.headers.get("Idempotency-Key"),
    );
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
  });
});
