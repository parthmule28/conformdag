import type { GateResult } from "../../api";
import { Banner, StatusBadge, Table, Td, Th } from "../ui";

export interface GateResultPanelProps {
  /** The gate verdict exactly as recorded by the server, or null when none exists. */
  gateResult: GateResult | null;
  /** `complete` from the loaded report; null when no report artifact was loaded. */
  reportComplete: boolean | null;
  /** True when the report endpoint returned 404 (artifact pruned or never written). */
  artifactUnavailable: boolean;
  /** True while the scan is queued or running. */
  scanActive: boolean;
}

function NotEvaluatedReason({
  scanActive,
  reportComplete,
  artifactUnavailable,
}: {
  scanActive: boolean;
  reportComplete: boolean | null;
  artifactUnavailable: boolean;
}) {
  if (scanActive) {
    return (
      <Banner variant="info" title="Gates not evaluated">
        <p>The gate is evaluated once the scan finishes.</p>
      </Banner>
    );
  }
  if (artifactUnavailable) {
    return (
      <Banner variant="warning" title="Gates not evaluated">
        <p>
          The canonical report artifact for this scan is unavailable, so its recorded gate result
          cannot be shown.
        </p>
      </Banner>
    );
  }
  return (
    <Banner variant="info" title="Gates not evaluated">
      <p>
        {reportComplete === false
          ? "The scan did not finish evaluating every policy, so no gate verdict was recorded."
          : "No gate result was recorded for this scan. Gates are evaluated when a policy pack is configured."}
      </p>
    </Banner>
  );
}

/**
 * Renders the gate verdict exactly as the server recorded it. The UI never
 * constructs a replacement gate result: without a server verdict the panel
 * shows "Not evaluated" and explains why.
 */
export function GateResultPanel({
  gateResult,
  reportComplete,
  artifactUnavailable,
  scanActive,
}: GateResultPanelProps) {
  return (
    <section data-tour="gate-result" aria-label="Gate result" className="grid gap-3">
      {gateResult === null ? (
        <>
          <NotEvaluatedReason
            scanActive={scanActive}
            reportComplete={reportComplete}
            artifactUnavailable={artifactUnavailable}
          />
          <p className="text-sm text-muted">
            Gate verdict: <span className="font-medium text-ink">Not evaluated</span>
          </p>
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <StatusBadge status={gateResult.passed ? "PASS" : "FAIL"} />
            <span className="font-medium text-ink">
              {gateResult.passed ? "Gate passed" : "Gate failed"}
            </span>
            <span className="text-muted">
              Gate <span className="font-mono text-ink">{gateResult.gate_id}</span>
            </span>
          </div>
          <Table caption="Gate rules">
            <thead>
              <tr>
                <Th>Rule</Th>
                <Th>Verdict</Th>
                <Th>Detail</Th>
                <Th>Matching findings</Th>
              </tr>
            </thead>
            <tbody>
              {gateResult.rules.map((rule) => (
                <tr key={`${rule.rule_type}-${rule.detail}`}>
                  <Td className="font-mono">{rule.rule_type}</Td>
                  <Td>
                    <StatusBadge status={rule.passed ? "PASS" : "FAIL"} />
                  </Td>
                  <Td>{rule.detail}</Td>
                  <Td className="tabular-nums">{rule.matching_findings}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}
    </section>
  );
}
