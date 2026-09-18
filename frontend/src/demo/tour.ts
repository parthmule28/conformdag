/**
 * Pure state for the guided demo tour: activation parsing, query-preserving
 * location building, the ordered step list with stable `data-tour` targets,
 * the step-index reducer, and best-effort dismissal storage. No React, DOM
 * queries, API types, or platform display labels live here.
 */

export const TOUR_TARGETS = [
  "overview-signal",
  "repository-link",
  "scan-link",
  "gate-result",
  "finding-details",
  "finding-remediation",
  "policy-pack",
  "policy-gate",
  "suppression-active",
  "suppression-expired",
  "scan-export",
] as const;

export type TourTarget = (typeof TOUR_TARGETS)[number];

/** How "Tour next" moves from one step to the next. */
export type TourAdvance =
  | { kind: "retain" }
  | { kind: "navigate"; pathname: string }
  | { kind: "follow-link"; target: TourTarget }
  | { kind: "press-button"; target: TourTarget }
  | { kind: "revisit-link"; target: TourTarget };

export interface TourStep {
  id: string;
  title: string;
  body: string;
  target: TourTarget;
  advance: TourAdvance;
}

export const TOUR_STEPS: readonly TourStep[] = [
  {
    id: "overview",
    title: "Governance overview",
    body: "This console tracks repository health against your policy packs. The current failures signal where today's DAGs do not yet conform.",
    target: "overview-signal",
    advance: { kind: "follow-link", target: "repository-link" },
  },
  {
    id: "repository",
    title: "Repository health",
    body: "Every repository keeps a baseline and a scan history. The newest scan introduced failures against the active pack.",
    target: "scan-link",
    advance: { kind: "follow-link", target: "scan-link" },
  },
  {
    id: "gate",
    title: "Quality gate verdict",
    body: "Each completed scan records one gate verdict from its canonical report. This scan failed the pack's gate, so the findings below block it.",
    target: "gate-result",
    advance: { kind: "press-button", target: "finding-details" },
  },
  {
    id: "remediation",
    title: "Finding remediation",
    body: "A finding names its policy contract, source location, and a deterministic remediation payload teams can act on.",
    target: "finding-remediation",
    advance: { kind: "navigate", pathname: "/policies" },
  },
  {
    id: "policy-pack",
    title: "Policy packs",
    body: "Policies live in versioned packs with recorded provenance. Select the governing pack to inspect its rules.",
    target: "policy-pack",
    advance: { kind: "press-button", target: "policy-pack" },
  },
  {
    id: "policy-gate",
    title: "Quality gates",
    body: "A pack's gate turns individual policy verdicts into the pass or fail decision enforced at scan time.",
    target: "policy-gate",
    advance: { kind: "navigate", pathname: "/suppressions" },
  },
  {
    id: "suppression-active",
    title: "Active suppression",
    body: "Teams waive findings with owned, expiring suppressions. The platform enforces expiry when scans run.",
    target: "suppression-active",
    advance: { kind: "retain" },
  },
  {
    id: "suppression-expired",
    title: "Expired suppression",
    body: "Expired exceptions stay visible for audit but no longer waive their findings.",
    target: "suppression-expired",
    advance: { kind: "revisit-link", target: "scan-link" },
  },
  {
    id: "export",
    title: "Export the report",
    body: "Every scan produces portable report artifacts for downstream tooling.",
    target: "scan-export",
    advance: { kind: "retain" },
  },
];

export interface TourState {
  stepIndex: number;
  dismissed: boolean;
  /** Locations recorded when marked links were followed, keyed by marker. */
  recalled: Partial<Record<TourTarget, string>>;
  /** Demo route (pathname + search) each step was entered on, for Back. */
  routes: Record<number, string>;
}

export type TourAction =
  | { type: "next"; route: string }
  | { type: "back" }
  | { type: "skip" }
  | { type: "finish" }
  | { type: "restart" }
  | { type: "record-link"; target: TourTarget; href: string }
  | { type: "record-route"; stepIndex: number; route: string };

const DISMISSAL_KEY = "conformdag.demo-tour.dismissed";

export function isDemoTourEnabled(search: string): boolean {
  return new URLSearchParams(search).get("demo") === "1";
}

export function toDemoLocation(
  pathname: string,
  search: string,
): { pathname: string; search: string } {
  const params = new URLSearchParams(search);
  params.set("demo", "1");
  return { pathname, search: `?${params.toString()}` };
}

export function initialTourState(): TourState {
  return { stepIndex: 0, dismissed: loadDismissed(), recalled: {}, routes: {} };
}

export function tourReducer(state: TourState, action: TourAction): TourState {
  switch (action.type) {
    case "next": {
      const nextIndex = Math.min(state.stepIndex + 1, TOUR_STEPS.length - 1);
      return {
        ...state,
        stepIndex: nextIndex,
        routes: { ...state.routes, [nextIndex]: action.route },
      };
    }
    case "back":
      return { ...state, stepIndex: Math.max(state.stepIndex - 1, 0) };
    case "skip":
    case "finish":
      return { ...state, dismissed: true };
    case "restart":
      return { stepIndex: 0, dismissed: false, recalled: {}, routes: {} };
    case "record-link":
      return {
        ...state,
        recalled: { ...state.recalled, [action.target]: action.href },
      };
    case "record-route":
      return {
        ...state,
        routes: { ...state.routes, [action.stepIndex]: action.route },
      };
  }
}

/** Best-effort read; storage may be unavailable or blocked by the browser. */
export function loadDismissed(): boolean {
  try {
    return window.localStorage.getItem(DISMISSAL_KEY) === "1";
  } catch {
    return false;
  }
}

/** Best-effort write; a failed write never blocks the tour. */
export function storeDismissed(dismissed: boolean): void {
  try {
    if (dismissed) {
      window.localStorage.setItem(DISMISSAL_KEY, "1");
    } else {
      window.localStorage.removeItem(DISMISSAL_KEY);
    }
  } catch {
    return;
  }
}
