/**
 * Gate verdict rendering: the recorded server verdict is presented verbatim —
 * a passing gate shows the "Gate passed" heading with PASS badges, a failing
 * gate shows "Gate failed", and no verdict is never replaced by a derived one.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { GateResult } from "../../api";
import { GateResultPanel } from "./GateResultPanel";

const PASSING_GATE: GateResult = {
  gate_id: "release-readiness",
  passed: true,
  rules: [
    { rule_type: "max-findings", passed: true, detail: "0 failing finding(s), limit is 25", matching_findings: 0 },
  ],
};

const FAILING_GATE: GateResult = {
  gate_id: "baseline-gate",
  passed: false,
  rules: [
    { rule_type: "max-findings", passed: false, detail: "1 failing finding(s), limit is 0", matching_findings: 1 },
  ],
};

function renderGate(gateResult: GateResult | null): HTMLElement {
  render(
    <GateResultPanel
      gateResult={gateResult}
      reportComplete={true}
      artifactUnavailable={false}
      scanActive={false}
    />,
  );
  return screen.getByRole("region", { name: "Gate result" });
}

afterEach(cleanup);

describe("GateResultPanel", () => {
  it("presents a recorded passing verdict with the Gate passed heading", () => {
    const gate = renderGate(PASSING_GATE);

    expect(within(gate).getByText("Gate passed")).toBeInTheDocument();
    expect(within(gate).getAllByText("PASS")).toHaveLength(2);
    expect(within(gate).getByText("release-readiness")).toBeInTheDocument();
    const ruleRow = within(gate).getByRole("row", { name: /limit is 25/ });
    expect(within(ruleRow).getByText("PASS")).toBeInTheDocument();
    expect(within(gate).queryByText("Gate failed")).not.toBeInTheDocument();
    expect(within(gate).queryByText("Not evaluated")).not.toBeInTheDocument();
  });

  it("presents a recorded failing verdict with the Gate failed heading", () => {
    const gate = renderGate(FAILING_GATE);

    expect(within(gate).getByText("Gate failed")).toBeInTheDocument();
    expect(within(gate).getByRole("row", { name: /limit is 0/ })).toContainHTML("FAIL");
    expect(within(gate).queryByText("Gate passed")).not.toBeInTheDocument();
  });

  it("never derives a verdict when the server recorded none", () => {
    const gate = renderGate(null);

    expect(within(gate).getByText("Not evaluated")).toBeInTheDocument();
    expect(within(gate).queryByText("Gate passed")).not.toBeInTheDocument();
    expect(within(gate).queryByText("Gate failed")).not.toBeInTheDocument();
  });
});
