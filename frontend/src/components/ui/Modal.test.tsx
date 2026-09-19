/**
 * Modal focus contract: initial focus lands on the dialog panel (never the
 * header's dismiss control), the Tab trap still cycles the content, and
 * focus returns to the trigger when the dialog closes.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState, type ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { Button } from "./Button";
import { Modal } from "./Modal";

function ModalHarness(): ReactNode {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Open editor</Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Edit policy"
        footer={<Button onClick={() => setOpen(false)}>Save changes</Button>}
      >
        <Button variant="secondary" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </Modal>
    </>
  );
}

function openModal(): HTMLElement {
  render(<ModalHarness />);
  fireEvent.click(screen.getByRole("button", { name: "Open editor" }));
  return screen.getByRole("dialog", { name: "Edit policy" });
}

afterEach(cleanup);

describe("Modal focus contract", () => {
  it("lands initial focus on the dialog panel instead of the dismiss control", () => {
    const dialog = openModal();

    expect(dialog).toHaveFocus();
    expect(screen.getByRole("button", { name: "Close" })).not.toHaveFocus();
  });

  it("keeps Tab cycling through the content and wrapping at both edges", () => {
    const dialog = openModal();
    const closeButton = screen.getByRole("button", { name: "Close" });
    const saveButton = screen.getByRole("button", { name: "Save changes" });

    // Native Tab from the focused panel lands on the first focusable (Close);
    // jsdom does not move focus itself, so seed it explicitly.
    closeButton.focus();
    fireEvent.keyDown(closeButton, { key: "Tab", shiftKey: true });
    expect(saveButton).toHaveFocus();

    fireEvent.keyDown(saveButton, { key: "Tab" });
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Edit policy" })).not.toBeInTheDocument();
  });

  it("restores focus to the trigger when the dialog closes", () => {
    render(<ModalHarness />);
    const trigger = screen.getByRole("button", { name: "Open editor" });
    // A real click focuses the trigger; jsdom's fireEvent does not.
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Edit policy" })).toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole("dialog", { name: "Edit policy" }), { key: "Escape" });

    expect(screen.queryByRole("dialog", { name: "Edit policy" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
