/**
 * Guided demo tour: query activation, step navigation with query
 * preservation, back/skip/restart controls, marked-link and marked-button
 * advances, and the accessible paused state for missing targets. Fixtures
 * are plain nodes carrying stable `data-tour` markers; the platform API is
 * not involved or mocked.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { act, useState } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { DemoTour } from "./DemoTour";
import { isDemoTourEnabled, toDemoLocation, type TourTarget } from "./tour";

const FIRST_STEP_TITLE = "Governance overview";
const SECOND_STEP_TITLE = "Repository health";

const ALL_MARKERS: TourTarget[] = [
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
];

function LocationProbe() {
  const { pathname, search } = useLocation();
  return (
    <p data-testid="location">
      {pathname}
      {search}
    </p>
  );
}

function MarkerNode({ marker }: { marker: TourTarget }) {
  const [pressed, setPressed] = useState(false);
  if (marker === "repository-link") {
    return (
      <a data-tour={marker} href="/repos/repo-1">
        Seeded repository
      </a>
    );
  }
  if (marker === "scan-link") {
    return (
      <a data-tour={marker} href="/scans/scan-1">
        Seeded scan
      </a>
    );
  }
  if (marker === "scan-export") {
    return (
      <a data-tour={marker} href="/api/v1/scans/scan-1/report.json">
        JSON
      </a>
    );
  }
  if (marker === "finding-details" || marker === "policy-pack") {
    return (
      <button type="button" data-tour={marker} onClick={() => setPressed(true)}>
        {pressed ? `${marker} pressed` : marker}
      </button>
    );
  }
  return <div data-tour={marker}>{marker}</div>;
}

interface HarnessProps {
  initialEntries?: string[];
  markers?: TourTarget[];
}

function Harness({ initialEntries = ["/?demo=1"], markers = ALL_MARKERS }: HarnessProps) {
  return (
    <MemoryRouter initialEntries={initialEntries}>
      <LocationProbe />
      {markers.map((marker) => (
        <MarkerNode key={marker} marker={marker} />
      ))}
      <DemoTour maxWaitFrames={2} />
    </MemoryRouter>
  );
}

function tourDialog() {
  return screen.getByRole("dialog", { name: "ConformDAG demo tour" });
}

function clickNext(): void {
  fireEvent.click(screen.getByRole("button", { name: "Tour next" }));
}

function expectStepTitle(title: string): void {
  expect(tourDialog()).toHaveTextContent(title);
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe("tour activation helpers", () => {
  it("enables the tour only for the exact demo=1 query value", () => {
    expect(isDemoTourEnabled("?demo=1")).toBe(true);
    expect(isDemoTourEnabled("?pack=x&demo=1")).toBe(true);
    expect(isDemoTourEnabled("?demo=1&x=2")).toBe(true);
    expect(isDemoTourEnabled("")).toBe(false);
    expect(isDemoTourEnabled("?")).toBe(false);
    expect(isDemoTourEnabled("?demo=0")).toBe(false);
    expect(isDemoTourEnabled("?demo=true")).toBe(false);
    expect(isDemoTourEnabled("?demo=11")).toBe(false);
    expect(isDemoTourEnabled("?Demo=1")).toBe(false);
  });

  it("builds demo locations that preserve existing query parameters", () => {
    expect(toDemoLocation("/", "?demo=1")).toEqual({ pathname: "/", search: "?demo=1" });
    expect(toDemoLocation("/policies", "?demo=1")).toEqual({
      pathname: "/policies",
      search: "?demo=1",
    });
    const enriched = toDemoLocation("/policies", "?focus=gate");
    expect(enriched.pathname).toBe("/policies");
    expect(new URLSearchParams(enriched.search).get("focus")).toBe("gate");
    expect(new URLSearchParams(enriched.search).get("demo")).toBe("1");
    expect(toDemoLocation("/", "").search).toBe("?demo=1");
  });
});

describe("DemoTour gating", () => {
  it.each(["/", "/?demo=0", "/?demo=true", "/?demo=11", "/suppressions?pack=x"])(
    "renders nothing for %s",
    (entry) => {
      render(<Harness initialEntries={[entry]} />);
      expect(screen.queryByRole("dialog", { name: "ConformDAG demo tour" })).not.toBeInTheDocument();
    },
  );

  it("renders the first step for the demo query", () => {
    render(<Harness />);
    expectStepTitle(FIRST_STEP_TITLE);
    expect(tourDialog()).toHaveTextContent("policy packs");
    expect(screen.getByRole("button", { name: "Tour back" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Tour next" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Skip tour" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Restart tour" })).toBeEnabled();
  });

  it("runs no polling or highlight side effects when the demo query is absent", async () => {
    const { container } = render(<Harness initialEntries={["/"]} />);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 80));
    });
    expect(container.querySelector(".demo-tour-target")).toBeNull();
    const marker = container.querySelector('[data-tour="overview-signal"]');
    expect(marker).not.toBeNull();
    expect(marker).not.toHaveAttribute("aria-describedby");
    expect(
      screen.queryByRole("dialog", { name: "ConformDAG demo tour" }),
    ).not.toBeInTheDocument();
  });
});

describe("DemoTour navigation", () => {
  it("follows the marked repository link by href and preserves demo=1", () => {
    render(<Harness />);
    clickNext();
    expect(screen.getByTestId("location")).toHaveTextContent("/repos/repo-1?demo=1");
    expectStepTitle(SECOND_STEP_TITLE);
  });

  it("returns to the prior step with Back", () => {
    render(<Harness />);
    clickNext();
    clickNext();
    expectStepTitle("Quality gate verdict");
    fireEvent.click(screen.getByRole("button", { name: "Tour back" }));
    expectStepTitle(SECOND_STEP_TITLE);
    fireEvent.click(screen.getByRole("button", { name: "Tour back" }));
    expectStepTitle(FIRST_STEP_TITLE);
    expect(screen.getByRole("button", { name: "Tour back" })).toBeDisabled();
  });

  it("restores the prior tour route when Back crosses a page boundary", () => {
    render(<Harness />);
    clickNext();
    clickNext();
    expect(screen.getByTestId("location")).toHaveTextContent("/scans/scan-1?demo=1");
    fireEvent.click(screen.getByRole("button", { name: "Tour back" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/repos/repo-1?demo=1");
    expectStepTitle(SECOND_STEP_TITLE);
    fireEvent.click(screen.getByRole("button", { name: "Tour back" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/?demo=1");
    expectStepTitle(FIRST_STEP_TITLE);
    expect(screen.getByRole("button", { name: "Tour back" })).toBeDisabled();
  });

  it("invokes the marked Details button for the finding step", () => {
    render(<Harness />);
    clickNext();
    clickNext();
    clickNext();
    expect(screen.getByText("finding-details pressed")).toBeInTheDocument();
    expectStepTitle("Finding remediation");
  });

  it("completes the whole journey and dismisses on the final Next", () => {
    render(<Harness />);
    for (let index = 0; index < 8; index += 1) {
      clickNext();
    }
    expectStepTitle("Export the report");
    expect(screen.getByTestId("location")).toHaveTextContent("/scans/scan-1?demo=1");
    clickNext();
    expect(
      screen.queryByRole("dialog", { name: "ConformDAG demo tour" }),
    ).not.toBeInTheDocument();
  });

  it("hides the overlay on Skip and keeps a restart entry point", () => {
    render(<Harness />);
    clickNext();
    fireEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    expect(
      screen.queryByRole("dialog", { name: "ConformDAG demo tour" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restart tour" })).toBeInTheDocument();
  });

  it("restores step zero from the in-dialog Restart control", () => {
    render(<Harness />);
    clickNext();
    fireEvent.click(screen.getByRole("button", { name: "Restart tour" }));
    expectStepTitle(FIRST_STEP_TITLE);
    expect(screen.getByRole("button", { name: "Tour back" })).toBeDisabled();
  });

  it("restores step zero from the dismissed-state restart chip", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    fireEvent.click(screen.getByRole("button", { name: "Restart tour" }));
    expectStepTitle(FIRST_STEP_TITLE);
  });

  it("remembers dismissal across remounts without storage crashes", () => {
    const first = render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    first.unmount();
    render(<Harness />);
    expect(
      screen.queryByRole("dialog", { name: "ConformDAG demo tour" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restart tour" })).toBeInTheDocument();
  });

  it("keeps working when storage access throws", () => {
    const original = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("storage blocked");
      },
    });
    try {
      render(<Harness />);
      expectStepTitle(FIRST_STEP_TITLE);
      fireEvent.click(screen.getByRole("button", { name: "Skip tour" }));
      expect(
        screen.queryByRole("dialog", { name: "ConformDAG demo tour" }),
      ).not.toBeInTheDocument();
    } finally {
      if (original === undefined) {
        Reflect.deleteProperty(window, "localStorage");
      } else {
        Object.defineProperty(window, "localStorage", original);
      }
    }
  });
});

describe("DemoTour missing targets", () => {
  it("pauses safely when a step target never appears, offering only Restart and Skip", async () => {
    render(<Harness markers={["overview-signal", "repository-link"]} />);
    clickNext();
    expect(await screen.findByText("Tour paused")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tour next" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tour back" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restart tour" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Skip tour" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Restart tour" }));
    expectStepTitle(FIRST_STEP_TITLE);
    expect(screen.queryByText("Tour paused")).not.toBeInTheDocument();
  });

  it("pauses when the advance target itself is absent", async () => {
    render(<Harness markers={["overview-signal"]} />);
    clickNext();
    expect(await screen.findByText("Tour paused")).toBeInTheDocument();
  });
});
