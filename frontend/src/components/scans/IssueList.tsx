import type { ReportIssue } from "../../api";
import { Banner, Table, Td, Th } from "../ui";

/**
 * Run issues exactly as retained in the canonical report. Fatal issues and
 * EVALUATION_ERROR codes are called out explicitly; nothing here derives
 * scan outcomes.
 */
export function IssueList({ issues }: { issues: ReportIssue[] }) {
  const evaluationErrors = issues.filter((issue) => issue.code === "EVALUATION_ERROR");
  return (
    <div className="grid gap-3">
      {evaluationErrors.length > 0 && (
        <Banner variant="warning" title="EVALUATION_ERROR">
          <p>
            One or more policies failed to evaluate, so findings from those policies are missing
            from this scan.
          </p>
        </Banner>
      )}
      <Table
        caption="Run issues"
        empty={issues.length === 0}
        emptyMessage="The scan recorded no parse or evaluation issues."
      >
        <thead>
          <tr>
            <Th>Severity</Th>
            <Th>Code</Th>
            <Th>Message</Th>
            <Th>Path</Th>
            <Th>Phase</Th>
          </tr>
        </thead>
        <tbody>
          {issues.map((issue, index) => (
            <tr key={`${issue.code}-${issue.phase}-${index}`}>
              <Td>
                <span className={issue.fatal ? "font-medium text-fail" : "text-muted"}>
                  {issue.fatal ? "Fatal" : "Non-fatal"}
                </span>
              </Td>
              <Td className="font-mono">{issue.code}</Td>
              <Td className="break-words">{issue.message}</Td>
              <Td className="break-all font-mono">{issue.path ?? "\u2014"}</Td>
              <Td className="font-mono">{issue.phase}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}
