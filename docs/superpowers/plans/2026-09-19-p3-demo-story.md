# P3 Demo Story Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver `mise run demo`, a disposable local platform scenario, and an opt-in guided dashboard tour that explains ConformDAG's governance loop.

**Architecture:** Extract the existing Playwright-only disposable-platform setup into a reusable `conformdag.platform.demo` module that creates source/pack/workspace data, migrates SQLite through Alembic, and drives scans through the production worker. A small Python launcher owns the temporary directory, worker lifecycle, port check, Uvicorn server, and browser opening. The React app enables a client-only tour only for `?demo=1`; target attributes and route-derived stable IDs allow it to navigate the seeded scenario without a backend contract or schema change.

**Tech Stack:** Python 3.12, Typer-adjacent script entry point, Uvicorn, SQLAlchemy/Alembic, FastAPI, React 19, React Router, TanStack Query, Tailwind v4, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-19-p3-demo-story-design.md`

## Global Constraints

- `scan_repository()` remains the only evaluation path.
- Alembic remains the sole platform schema-creation path; never call `Base.metadata.create_all()`.
- The demo uses the existing typed `/api/v1` contract; frontend code must not reach Python models or SQLite.
- Demo execution requires no Docker daemon, external provider, network connection, or external secret.
- Seeded reports are produced by the production worker/runner; do not insert report or finding rows as fixture data.
- The demo uses a temporary workspace and SQLite file and cleans both up on normal exit and interruption.
- The existing `scripts/e2e_platform.py` and the demo command must share seed primitives.
- Tour activation is `?demo=1`, tour state is browser-local, and tour-controlled navigation preserves the parameter.
- Tour navigation and tests use stable IDs or `data-tour` target markers, never visible display labels.
- Python must remain Pyright strict; TypeScript must remain strict; core coverage must stay at least 90%.

---

## File Structure

- Create `src/conformdag/platform/demo.py` — reusable workspace builder, production-faithful scan seed orchestration, immutable scenario IDs, loopback port validation, and demo process lifecycle helpers.
- Create `scripts/demo.py` — argparse entry point that starts the disposable demo, opens `/?demo=1`, and performs shutdown cleanup.
- Modify `scripts/e2e_platform.py` — replace private workspace/seed duplication with `platform.demo` primitives while retaining e2e-specific fixed token/host/port defaults.
- Modify `mise.toml` — expose `mise run demo` and document its foreground behavior in its task description.
- Modify `tests/test_platform.py` — test only reusable Python seed/lifecycle behavior alongside other platform tests.
- Create `frontend/src/demo/tour.ts` — pure tour step types, activation parsing, local-state reducer, stable selector helpers, and route resolution.
- Create `frontend/src/demo/DemoTour.tsx` — accessible overlay/controller that waits for targets, navigates, opens the seeded finding detail, and safely exits when a target is absent.
- Create `frontend/src/demo/DemoTour.test.tsx` — focused component/reducer tests for activation, navigation, back/skip/restart, and missing-target handling.
- Modify `frontend/src/App.tsx` — mount the tour inside the existing router only when `demo=1` is present.
- Modify existing page/component files — add narrow `data-tour` hooks to the overview signal, seeded-repository link, scan gate, finding Details control/detail panel, policy pack/gate region, suppression row, and scan export action.
- Create `frontend/e2e/demo-tour.spec.ts` — Playwright golden journey against the reusable seeded platform and real typed API.
- Modify `README.md` and `docs/user-guide.md` — lead with the demo and document command options, data lifetime, cleanup, and deployment distinction.

## Task 1: Reusable production-faithful demo scenario

**Files:**
- Create: `src/conformdag/platform/demo.py`
- Modify: `scripts/e2e_platform.py`
- Modify: `tests/test_platform.py`

**Interfaces:**
- Produces `DemoWorkspace(root: Path, workspace_path: Path, pack_path: Path, dsn: str)` and `DemoScenario(ids: Mapping[str, str])` dataclasses.
- Produces `build_demo_workspace(root: Path) -> DemoWorkspace`, `seed_demo_scenario(workspace: DemoWorkspace) -> DemoScenario`, and `start_demo_worker(workspace: DemoWorkspace) -> threading.Thread`.
- `seed_demo_scenario` completes its baseline, probe, and current scans through `run_worker_once`; `start_demo_worker` starts the normal asynchronous worker for interactive scans after the seed is ready.
- Consumes `initialize_session_factory()`, `create_session_factory()`, `run_worker_once()`, `run_worker()`, `request_shutdown()`, and `create_app()` from the existing platform; no raw report/finding insertion.
- `scripts/e2e_platform.py` consumes `build_demo_workspace`, `seed_demo_scenario`, and `start_demo_worker` rather than owning duplicated DAG, pack, or row construction.

- [x] **Step 1: Write failing tests for a valid scenario and real scan outcomes**

  Add imports for `build_demo_workspace` and `seed_demo_scenario` in `tests/test_platform.py`. Add a test that builds under `tmp_path`, calls the builder, and asserts the workspace, standards file, and pack exist. Add a seed test that invokes the scenario function, then loads `RepositoryRow`, `ScanRow`, and `FindingRow` and proves:

  ```python
  def test_demo_seed_creates_baseline_and_later_gate_failure(tmp_path: Path) -> None:
      workspace = build_demo_workspace(tmp_path)
      scenario = seed_demo_scenario(workspace)
      factory = create_session_factory(workspace.dsn)
      with factory() as session:
          repository = session.get(RepositoryRow, scenario.ids["repository"])
          baseline = session.get(ScanRow, scenario.ids["baseline_scan"])
          current = session.get(ScanRow, scenario.ids["current_scan"])
          assert repository is not None and repository.baseline_scan_id == baseline.id
          assert baseline is not None and baseline.complete is True
          assert current is not None and current.complete is True
          assert current.gate_result is not None and current.gate_result["passed"] is False
          assert session.query(FindingRow).filter_by(scan_id=current.id).count() > 0
  ```

  Add a second test that asserts the active and expired `SuppressionRow` records are real seed records, with timestamps respectively after and before `utcnow()`, and that the active record matches a finding from the current report rather than a synthetic fingerprint.

- [x] **Step 2: Run the new platform tests and verify they fail**

  Run: `mise exec -- uv run pytest tests/test_platform.py -k 'demo_seed' -x --tb=short`

  Expected: FAIL because `conformdag.platform.demo` does not exist.

- [x] **Step 3: Implement the scenario module**

  Create `src/conformdag/platform/demo.py`. Move the standards text, pack generation, workspace construction, terminal-status wait, and worker-thread setup out of `scripts/e2e_platform.py`. Keep paths rooted beneath the caller-provided `root`.

  Build a conforming initial DAG with an owner and both required tags. Queue and complete it through `run_worker_once` first; set it as `RepositoryRow.baseline_scan_id`. Then alter the DAG to create at least two deterministic findings, complete a probe scan through `run_worker_once`, and configure the pack gate with `max-findings: 0` so its recorded gate result fails. Determine the active suppression's exact fingerprint from that real report, add the suppression through the platform's existing durable suppression model, and queue/complete the final current scan through `run_worker_once` so its report demonstrates both an unsuppressed gate-blocking finding and a suppressed finding. Also create a distinct expired suppression for the inventory state.

  The public scenario IDs must include at least `repository`, `baseline_scan`, `current_scan`, `active_suppression`, and `expired_suppression`. Use `Mapping[str, str]` behind a frozen dataclass, not display names. Initialise the database only through `initialize_session_factory(workspace.dsn)`, run scans through the worker/runner, and raise `RuntimeError` with the scan ID and observed state for unexpected terminal outcomes or deadline expiration.

  Replace `scripts/e2e_platform.py` private constants and seed functions with calls into the module. It remains responsible only for argument parsing, `TemporaryDirectory`, `PlatformSettings`, Uvicorn configuration, and joining the shared worker at shutdown.

- [x] **Step 4: Run focused tests and static checks**

  Run:

  ```bash
  mise exec -- uv run pytest tests/test_platform.py -k 'demo_seed' -x --tb=short
  mise exec -- uv run pyright src/conformdag/platform/demo.py scripts/e2e_platform.py tests/test_platform.py
  ```

  Expected: PASS with 0 Pyright errors.

- [x] **Step 5: Commit the reusable scenario**

  ```bash
  git add src/conformdag/platform/demo.py scripts/e2e_platform.py tests/test_platform.py
  git commit -m "feat: extract reusable demo platform scenario"
  ```

## Task 2: Disposable `mise run demo` launcher

**Files:**
- Create: `scripts/demo.py`
- Modify: `mise.toml`
- Modify: `tests/test_platform.py`

**Interfaces:**
- `scripts/demo.py` accepts `--host` (default `127.0.0.1`), `--port` (default `8642`), `--open/--no-open` (default open), and `--token` (a loopback-only disposable default).
- It consumes `DemoWorkspace`, scenario seeding, worker startup, `PlatformSettings`, and `create_app()`.
- It exposes `ensure_port_available(host: str, port: int) -> None` and `demo_url(host: str, port: int) -> str` for unit testing.

- [x] **Step 1: Write failing launcher tests**

  Add tests that hold a loopback socket open and assert `ensure_port_available` raises `RuntimeError` containing the requested host and port. Add pure URL tests:

  ```python
  def test_demo_url_enables_the_client_tour() -> None:
      assert demo_url("127.0.0.1", 8642) == "http://127.0.0.1:8642/?demo=1"
  ```

  Monkeypatch the launcher’s `webbrowser.open` and server factory in a focused test; assert that `--no-open` never invokes the browser and the finally path invokes `request_shutdown`, joins the worker, and exits the temporary-directory context.

- [x] **Step 2: Run the launcher tests and verify they fail**

  Run: `mise exec -- uv run pytest tests/test_platform.py -k 'demo_url or demo_port or demo_launcher' -x --tb=short`

  Expected: FAIL because `scripts.demo` and its helpers do not exist.

- [x] **Step 3: Implement the launcher and Mise task**

  Create `scripts/demo.py` with `argparse`; keep it import-safe by importing Uvicorn and platform dependencies within `main()`. Bind-test the requested loopback endpoint before seeding to report an occupied port early. Create the temporary root, build/seed the scenario, start the worker, construct `PlatformSettings(dsn=workspace.dsn, admin_token=args.token, workspace=workspace.workspace_path)`, and serve the real app with `uvicorn.Server`.

  Print the URL from `demo_url()`, state that the instance is loopback-only/disposable, state the token is local demo-only, and print Ctrl-C cleanup instructions. If `--open` is true, call `webbrowser.open(url)` only after seeding succeeds and immediately before server run. In `finally`, set Uvicorn exit, call `request_shutdown()`, join the worker with a bounded timeout, and allow `TemporaryDirectory` cleanup. Catch `OSError` and Uvicorn startup errors at the entry-point boundary and return a nonzero exit with a concise actionable message.

  Add to `mise.toml`:

  ```toml
  [tasks.demo]
  description = "Start a disposable local ConformDAG demo (Ctrl-C removes its seeded state)"
  run = "uv run python scripts/demo.py"
  ```

- [x] **Step 4: Run launcher tests and manually smoke the command**

  Run:

  ```bash
  mise exec -- uv run pytest tests/test_platform.py -k 'demo_url or demo_port or demo_launcher' -x --tb=short
  timeout 20 mise run demo -- --no-open --port 8765
  ```

  Expected: tests PASS; smoke output prints `http://127.0.0.1:8765/?demo=1`, starts after the seed completes, and cleans up when `timeout` interrupts it.

- [x] **Step 5: Commit the launcher**

  ```bash
  git add scripts/demo.py mise.toml tests/test_platform.py
  git commit -m "feat: add disposable local demo command"
  ```

## Task 3: Client-side guided-tour controller and stable targets

**Files:**
- Create: `frontend/src/demo/tour.ts`
- Create: `frontend/src/demo/DemoTour.tsx`
- Create: `frontend/src/demo/DemoTour.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/OverviewPage.tsx`
- Modify: `frontend/src/components/overview/RecentScans.tsx`
- Modify: `frontend/src/pages/RepositoryPage.tsx`
- Modify: `frontend/src/components/repositories/ScanHistoryTable.tsx`
- Modify: `frontend/src/pages/ScanPage.tsx`
- Modify: `frontend/src/components/findings/FindingsTable.tsx`
- Modify: `frontend/src/components/findings/FindingDetailPanel.tsx`
- Modify: `frontend/src/pages/PoliciesPage.tsx`
- Modify: `frontend/src/components/policies/PackList.tsx`
- Modify: `frontend/src/components/scans/GateResultPanel.tsx`
- Modify: `frontend/src/pages/SuppressionsPage.tsx`
- Modify: `frontend/src/components/suppressions/SuppressionTable.tsx`

**Interfaces:**
- `isDemoTourEnabled(search: string): boolean` returns true only when `URLSearchParams(search).get("demo") === "1"`.
- `TourStep` has `id`, `title`, `body`, `target`, and an `advance` resolver that either retains the route, follows a marked same-origin link, or opens a marked Details button.
- `DemoTour` uses React Router `useLocation`/`useNavigate`, renders only for enabled URLs, and exposes buttons named `Tour next`, `Tour back`, `Skip tour`, and `Restart tour`.
- Stable `data-tour` markers identify `overview-signal`, `repository-link`, `scan-link`, `gate-result`, `finding-details`, `finding-remediation`, `policy-pack`, `policy-gate`, `suppression-active`, `suppression-expired`, and `scan-export`.

- [x] **Step 1: Write failing unit tests for activation and controller behavior**

  Create `frontend/src/demo/DemoTour.test.tsx`. Test activation with `?demo=1`, rejection for empty/search values other than exactly `1`, first-step rendering, Next following a fixture anchor with `data-tour="repository-link"`, Back returning to the prior step, Skip hiding the overlay, Restart restoring step zero, and a missing target rendering an accessible “Tour paused” state with only Restart/Skip actions.

  Use a `MemoryRouter` test harness and stable `data-tour` nodes; do not mock the platform API. Example assertion:

  ```tsx
  render(<Harness initialEntries={["/?demo=1"]} />);
  await user.click(screen.getByRole("button", { name: "Tour next" }));
  expect(screen.getByRole("dialog", { name: "ConformDAG demo tour" })).toHaveTextContent(
    "Repository health",
  );
  ```

- [x] **Step 2: Run the focused frontend tests and verify they fail**

  Run: `cd frontend && npm test -- DemoTour.test.tsx`

  Expected: FAIL because the demo-tour module does not exist.

- [x] **Step 3: Implement pure tour state and accessible overlay**

  In `tour.ts`, implement the search parser, a typed ordered step list, query-param-preserving `toDemoLocation(pathname: string, search: string)`, and pure step-index reducer. Each step declares an explicit advance action: retain route, follow a marked anchor `href`, or invoke a marked button. Use `localStorage` only for optional dismissed/restart state; protect reads with `try/catch` and never require storage availability.

  In `DemoTour.tsx`, render a labelled non-modal dialog that does not prevent ordinary navigation. On each step, poll no more frequently than animation frames until the current target exists; scroll it into view, place a visible outline/aria-describedby relationship, and focus the dialog’s heading. `Tour next` resolves marked links by their `href` (not their text) or invokes its declared marked button, then uses `navigate(toDemoLocation(...))` as appropriate; preserve `demo=1` for every tour-owned route transition. The policy step invokes the marked pack button before targeting its gate. The finding step invokes the marked Details button so the existing `FindingDetailPanel` modal displays the real remediation payload, then targets its `data-tour="finding-remediation"` section. No tour code imports API types, Python code, or seed display labels.

  Mount `<DemoTour />` inside `BrowserRouter` in `App.tsx`; it returns `null` unless the exact query parameter enables it. Add only `data-tour` attributes to existing components: overview metric/card, existing repository and scan links, gate section, finding Details button/remediation section, selected pack button, gate panel, active/expired seeded suppression rows, and export anchor. Preserve all existing labels, click handlers, routes, and non-demo behavior.

- [x] **Step 4: Run frontend unit and type checks**

  Run:

  ```bash
  cd frontend && npm test -- DemoTour.test.tsx
  cd frontend && npm run build
  ```

  Expected: PASS; TypeScript remains strict through the build.

- [x] **Step 5: Commit the guided-tour implementation**

  ```bash
  git add frontend/src/App.tsx frontend/src/demo frontend/src/pages frontend/src/components
  git commit -m "feat: add guided demo tour"
  ```

## Task 4: Browser golden journey using the shared demo scenario

**Files:**
- Create: `frontend/e2e/demo-tour.spec.ts`
- Modify: `frontend/e2e/fixtures.ts`
- Modify: `frontend/playwright.config.ts`
- Modify: `scripts/e2e_platform.py`

**Interfaces:**
- The test consumes the existing same-origin `repositoryByName`, `scanHistory`, and `firstFinding` helpers plus the marked tour buttons and targets.
- The backend web server continues to start `scripts/e2e_platform.py`, now backed by `platform.demo`.
- The journey never relies on a visible seeded repository name, policy title, scan ID, or suppression reason to locate a target.

- [x] **Step 1: Write the failing end-to-end tour test**

  Add `frontend/e2e/demo-tour.spec.ts`. Resolve the repository/current scan/finding from real `/api/v1` responses, then open `/?demo=1`. Click `Tour next` through the overview, repository, scan/gate, finding/remediation, policy/gate, suppression, and export stages. At each stage assert the expected `data-tour` target is visible and the URL keeps `demo=1`. Assert the finding modal contains a remediation section, the gate has a recorded failed result, active and expired suppression markers are distinct, and the JSON export anchor has a scan export URL. Finally assert Skip hides the dialog and Restart returns it to the overview step.

- [x] **Step 2: Run the new Playwright test and verify it fails**

  Run: `cd frontend && npm run e2e -- demo-tour.spec.ts`

  Expected: FAIL because the tour/markers are absent.

- [x] **Step 3: Make e2e startup consume the shared scenario and stabilize the journey**

  Update the Playwright config comments and `scripts/e2e_platform.py` only as needed to reflect the shared module; retain fixed localhost ports and the healthcheck. Extend `fixtures.ts` with typed helpers that resolve the current completed scan, matching active/expired suppressions, and a finding by API data—not human labels. Do not add frontend API routes, network mocks, sleeps, or selectors based on generated display text.

- [x] **Step 4: Run the focused and existing browser suites**

  Run:

  ```bash
  cd frontend && npm run typecheck:e2e
  cd frontend && npm run e2e -- demo-tour.spec.ts
  cd frontend && npm run e2e
  ```

  Expected: PASS in Chromium; existing journeys remain green against the refactored seed process.

- [x] **Step 5: Commit the golden journey**

  ```bash
  git add frontend/e2e frontend/playwright.config.ts scripts/e2e_platform.py
  git commit -m "test: cover demo tour in browser journey"
  ```

## Task 5: Demo-first documentation and final verification

**Files:**
- Modify: `README.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/roadmap.md`

**Interfaces:**
- README documents `mise run setup` followed by `mise run demo` as the local source-checkout experience.
- User guide documents the launcher’s `--port`, `--open/--no-open`, temporary-state cleanup, loopback-only behavior, and distinction from Docker Compose.
- Roadmap marks P3 complete only after the command, tour, documentation, and tests land.

- [x] **Step 1: Write failing documentation assertions/checklist**

  Add a short test in `tests/test_cli.py` or a focused `tests/test_smoke.py` text-contract test that reads `mise.toml`, `README.md`, and `docs/user-guide.md` and asserts they contain `mise run demo`, `--no-open`, and the Docker Compose distinction. This protects the documented command without testing prose layout.

- [x] **Step 2: Run the documentation test and verify it fails**

  Run: `mise exec -- uv run pytest tests/test_smoke.py -k demo -x --tb=short`

  Expected: FAIL because demo documentation text is absent.

- [x] **Step 3: Update docs and roadmap**

  Move a concise “Run the demo” section immediately after the README product introduction. Show:

  ```bash
  mise run setup
  mise run demo
  ```

  Explain the browser opens to a disposable local dashboard and guide the reader through overview, gate, finding/remediation, policy, suppression, and export. Keep production Compose instructions under the governance-platform section.

  Add a user-guide “Local product demo” section with `mise run demo -- --no-open --port 8765`, temporary SQLite/workspace lifecycle, Ctrl-C cleanup, no Docker/credentials/network requirement, and the statement that it is not a production deployment path. Mark P3 shipped in `docs/roadmap.md` only after these changes are verified.

- [x] **Step 4: Run all required verification**

  Run:

  ```bash
  mise run check
  mise run test:coverage
  cd frontend && npm run build && npm run e2e
  git diff --check
  ```

  Expected: all commands PASS; coverage is at least 90%; the full browser suite passes; and there is no whitespace error.

- [x] **Step 5: Commit documentation and P3 completion evidence**

  ```bash
  git add README.md docs/user-guide.md docs/roadmap.md tests/test_smoke.py
  git commit -m "docs: lead with disposable product demo"
  ```

## Plan Self-Review

- **Spec coverage:** Task 1 implements production-migration/worker/scan seeding, baseline/current reports, policy/gate, and active/expired suppressions. Task 2 implements disposable local process, port behavior, URL, browser opening, and cleanup. Task 3 implements the query-gated, browser-local accessible tour and stable targets. Task 4 verifies the complete real browser route and preservation of demo activation. Task 5 leads docs with the demo, documents production separation, updates the roadmap, and runs all gates.
- **Completeness scan:** Every task has concrete files, interfaces, commands, expected results, and implementation instructions.
- **Type consistency:** `DemoWorkspace`/`DemoScenario` originate in Task 1 and are consumed by Task 2; `isDemoTourEnabled`, `toDemoLocation`, `TourStep`, and the marker names originate in Task 3 and are consumed by Task 4.
