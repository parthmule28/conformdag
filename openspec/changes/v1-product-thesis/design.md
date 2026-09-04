## Context

See `proposal.md` for why. Today ADR 0001 principle 5 forbids a dashboard until usage
justifies it, and `docs/roadmap.md` describes dashboard as a future online service
with multi-user auth. 1.0.0 specs require local `serve` plus a dashboard (see
`specs/org-governance-1-0/spec.md`). This change is documentation and ADR only.

## Goals / Non-Goals

**Goals:**

- Make the 1.0.0 product contract reviewable (spec + ADR) before `workspace-and-serve`.
- Supersede ADR 0001 principle 5 **in part** (dashboard is in 1.0.0; plugin registry
  and multi-pack composition remain deferred unless a later ADR says otherwise).
- Align roadmap language with self-hosted OSS, not ConformDAG SaaS.

**Non-Goals:**

- Implementing `conformdag serve`, UI, agent, or GitHub Action.
- Choosing FastAPI, SPA framework, or history store (those belong in
  `workspace-and-serve` / `agent-pack-and-fix`).

## Decisions

1. **Product spec lives in OpenSpec** (`org-governance-1-0`) so later deltas can
   tighten journeys without rewriting the thesis ADR every time. Alternative:
   ADR-only. Rejected — ADRs are durable decisions; behavioral SHALLs belong in
   specs.

2. **ADR 0002 is Accepted** when this change is applied. ADR 0001 stays Accepted
   with an explicit superseded-in-part note on principle 5. Alternative: rewrite
   0001 in place. Rejected — history of the beta CLI principles should remain
   readable.

3. **Dashboard is a 1.0.0 MUST in the spec**, implemented in a subsequent change.
   Alternative: ship 1.0.0 CLI-only. Rejected by product thesis (org review journey D).

4. **MCP is not a 1.0.0 MUST.** Alternative: block 1.0.0 on MCP. Rejected — Cursor
   integration is a later adapter; dashboard is the review UI.

5. **Agent extra and BYOK** stay optional for `scan`; pack authoring and `fix` are
   still 1.0.0 MUST capabilities (install extra is allowed).

## Risks / Trade-offs

- [Spec over-constrains later design] → Spec states observable product behavior, not
  HTTP routes or React. Serve command name is allowed as a CLI contract.
- [ADR 0001 readers miss the supersession] → 0001 gets a status note; 0002 links back.
- [Roadmap still mentions “online service”] → Rewrite those bullets in this change.

## Migration Plan

Apply docs on `main` (this change). Follow with `workspace-and-serve` which MUST
satisfy journey D. No runtime rollback.

## Open Questions

Deferred to later changes (do not block this spec):

- Workspace file location and format
- Dashboard process model (bind address, Docker)
- UI and history-store implementation
- GitHub Action packaging (composite vs separate repo)
