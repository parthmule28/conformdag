import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Input } from "./FormControls";

afterEach(cleanup);

describe("form control accessibility contract", () => {
  it("keeps explicit ids and composes generated descriptions with caller descriptions", () => {
    render(
      <Input
        id="admin-token"
        label="Admin token"
        hint="Stored only for this browser session."
        error="The token is invalid."
        aria-describedby="external-help"
      />,
    );

    const input = screen.getByRole("textbox", { name: "Admin token" });
    expect(input).toHaveAttribute("id", "admin-token");
    expect(screen.getByText("Admin token").closest("label")).toHaveAttribute("for", "admin-token");
    expect(input).toHaveAttribute("aria-describedby", "admin-token-hint admin-token-error external-help");
    expect(input).toHaveAttribute("aria-invalid", "true");
  });
});
