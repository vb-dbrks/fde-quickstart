import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ReviewCard } from "@/agent/components";

it("keeps generated data provisional until an explicit edited acceptance", async () => {
  const accept = vi.fn(async () => {});
  const reject = vi.fn(async () => {});
  render(
    <ReviewCard title="Draft" value={{ title: "Original" }} accept={accept} reject={reject} />,
  );
  expect(accept).not.toHaveBeenCalled();
  const user = userEvent.setup();
  await user.click(screen.getByText("Edit before accepting"));
  const input = screen.getByLabelText("Edit Draft");
  await user.clear(input);
  await user.paste('{"title":"Edited"}');
  await user.click(screen.getByRole("button", { name: "Accept" }));
  expect(accept).toHaveBeenCalledWith({ title: "Edited" });
  expect(reject).not.toHaveBeenCalled();
});

it("never accepts malformed edited JSON", async () => {
  const accept = vi.fn(async () => {});
  render(
    <ReviewCard
      title="Draft"
      value={{ title: "Original" }}
      accept={accept}
      reject={async () => {}}
    />,
  );
  const user = userEvent.setup();
  await user.click(screen.getByText("Edit before accepting"));
  await user.clear(screen.getByLabelText("Edit Draft"));
  await user.click(screen.getByRole("button", { name: "Accept" }));
  expect(await screen.findByRole("alert")).toBeVisible();
  expect(accept).not.toHaveBeenCalled();
});
