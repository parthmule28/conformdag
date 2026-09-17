# Final Whole-Branch Review

## Verdict

- P1: Not Ready as-is.
- One Important finding blocks readiness; no Critical findings.

## Important

- `PackService.upsert_policy()` validates only the reconstructed `Policy`, not
  the reconstructed `PolicyPack`. An API mutation can therefore persist an
  unknown evaluator kind; subsequent scans fail closed, listing returns a
  server error, and recovery mutations are blocked. The post-mutation pack must
  pass `validate_policy_pack()` before `_write_pack()` and reject without
  touching disk.

## Same-Wave Minor

- The CLI evaluates and embeds a passing `gate_result` even when the report is
  incomplete. Skip gate evaluation for incomplete reports so the artifact
  cannot claim a passing gate alongside `complete: false`.

## Deferred / Residual

- Other recorded deferred Minors remain non-blocking per the final review,
  including worker poll validation, reused explicit DAG aliases, proposed-only
  span errors, and runtime/Postgres verification limits.
