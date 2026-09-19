/**
 * Client-only guided tour for the demo scenario. Renders only when the exact
 * `?demo=1` query parameter is present, keeps all state browser-local, and
 * never blocks ordinary navigation: it is a labelled non-modal dialog plus a
 * visible outline on the current step's `data-tour` target. Advances resolve
 * marked links by href, marked buttons by click, or explicit tour-owned
 * routes, always preserving `demo=1`. A step whose target never appears ends
 * in an accessible paused state offering only Restart and Skip.
 */
import { useEffect, useId, useReducer, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Button } from "../components/ui";
import {
  TOUR_STEPS,
  initialTourState,
  isDemoTourEnabled,
  storeDismissed,
  toDemoLocation,
  tourReducer,
  type TourTarget,
} from "./tour";

const DIALOG_LABEL = "ConformDAG demo tour";
const DEFAULT_MAX_WAIT_FRAMES = 300;
/** Pathname of the overview page, where the first tour step's target lives. */
const FIRST_STEP_PATHNAME = "/";

export interface DemoTourProps {
  /** Animation-frame budget for waiting on a step target before pausing. */
  maxWaitFrames?: number;
}

function markerSelector(target: TourTarget): string {
  return `[data-tour="${target}"]`;
}

function highlightTarget(element: HTMLElement, describedById: string): () => void {
  element.classList.add("demo-tour-target");
  const previousDescribedBy = element.getAttribute("aria-describedby");
  element.setAttribute(
    "aria-describedby",
    previousDescribedBy === null ? describedById : `${previousDescribedBy} ${describedById}`,
  );
  return () => {
    element.classList.remove("demo-tour-target");
    if (previousDescribedBy === null) {
      element.removeAttribute("aria-describedby");
    } else {
      element.setAttribute("aria-describedby", previousDescribedBy);
    }
  };
}

export function DemoTour({ maxWaitFrames = DEFAULT_MAX_WAIT_FRAMES }: DemoTourProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const enabled = isDemoTourEnabled(location.search);
  const [state, dispatch] = useReducer(tourReducer, undefined, initialTourState);
  const [paused, setPaused] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const bodyId = useId();

  const step = TOUR_STEPS[state.stepIndex];
  const target = step?.target;

  useEffect(() => {
    if (!enabled || state.dismissed || paused || target === undefined) {
      return undefined;
    }
    let cancelled = false;
    let handle: number | null = null;
    let frames = 0;
    let restoreHighlight: (() => void) | null = null;
    const tick = (): void => {
      if (cancelled) {
        return;
      }
      const element = document.querySelector<HTMLElement>(markerSelector(target));
      if (element !== null) {
        restoreHighlight = highlightTarget(element, bodyId);
        if (typeof element.scrollIntoView === "function") {
          element.scrollIntoView({ block: "center" });
        }
        headingRef.current?.focus();
        return;
      }
      frames += 1;
      if (frames >= maxWaitFrames) {
        setPaused(true);
        return;
      }
      handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      if (handle !== null) {
        cancelAnimationFrame(handle);
      }
      restoreHighlight?.();
    };
  }, [enabled, state.dismissed, state.stepIndex, paused, target, maxWaitFrames, bodyId]);

  // Remember the route each step starts on so Back can restore it; step zero
  // is recorded once at activation from the current location.
  useEffect(() => {
    if (!enabled || state.dismissed || state.routes[0] !== undefined) {
      return;
    }
    dispatch({
      type: "record-route",
      stepIndex: 0,
      route: `${location.pathname}${location.search}`,
    });
  }, [enabled, state.dismissed, state.routes, location.pathname, location.search]);

  if (step === undefined) {
    return null;
  }

  const restart = (): void => {
    // The first step's target lives on the overview route, so restart must
    // navigate there (keeping the demo query) before resetting state;
    // otherwise a restart from another route immediately re-pauses.
    const to = toDemoLocation(FIRST_STEP_PATHNAME, location.search);
    storeDismissed(false);
    setPaused(false);
    navigate(to);
    dispatch({ type: "restart" });
  };

  const skip = (): void => {
    storeDismissed(true);
    dispatch({ type: "skip" });
  };

  const handleBack = (): void => {
    if (state.stepIndex === 0) {
      return;
    }
    const previousRoute = state.routes[state.stepIndex - 1];
    if (previousRoute !== undefined) {
      navigate(previousRoute);
    }
    dispatch({ type: "back" });
  };

  const handleNext = (): void => {
    const advance = step.advance;
    let destination = `${location.pathname}${location.search}`;
    if (advance.kind === "follow-link") {
      const anchor = document.querySelector<HTMLAnchorElement>(markerSelector(advance.target));
      if (anchor === null) {
        setPaused(true);
        return;
      }
      const url = new URL(anchor.href, window.location.href);
      const to = toDemoLocation(url.pathname, url.search);
      destination = `${to.pathname}${to.search}`;
      dispatch({ type: "record-link", target: advance.target, href: destination });
      navigate(to);
    } else if (advance.kind === "press-button") {
      const button = document.querySelector<HTMLElement>(markerSelector(advance.target));
      if (button === null) {
        setPaused(true);
        return;
      }
      button.click();
    } else if (advance.kind === "revisit-link") {
      const recalledHref = state.recalled[advance.target];
      if (recalledHref === undefined) {
        setPaused(true);
        return;
      }
      destination = recalledHref;
      navigate(recalledHref);
    } else if (advance.kind === "navigate") {
      const to = toDemoLocation(advance.pathname, location.search);
      destination = `${to.pathname}${to.search}`;
      navigate(to);
    }
    if (state.stepIndex === TOUR_STEPS.length - 1) {
      storeDismissed(true);
      dispatch({ type: "finish" });
    } else {
      dispatch({ type: "next", route: destination });
    }
  };

  if (!enabled) {
    return null;
  }

  if (state.dismissed) {
    return (
      <Button
        size="sm"
        variant="secondary"
        className="fixed right-4 bottom-4 z-[60] shadow-overlay"
        onClick={restart}
      >
        Restart tour
      </Button>
    );
  }

  return (
    <section
      role="dialog"
      aria-label={DIALOG_LABEL}
      className="fixed right-4 bottom-4 z-[60] grid w-80 max-w-[calc(100vw-2rem)] gap-3 rounded-md border border-line bg-raised p-4 shadow-overlay"
    >
      {paused ? (
        <>
          <h2 ref={headingRef} tabIndex={-1} className="text-sm font-semibold text-ink">
            Tour paused
          </h2>
          <p id={bodyId} className="text-sm text-muted">
            The part of the demo this step points at is not on screen. Restart from the overview or
            skip the tour; every page stays usable.
          </p>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={skip}>
              Skip tour
            </Button>
            <Button size="sm" onClick={restart}>
              Restart tour
            </Button>
          </div>
        </>
      ) : (
        <>
          <p className="text-xs font-medium uppercase tracking-wide text-muted">
            Step {state.stepIndex + 1} of {TOUR_STEPS.length}
          </p>
          <h2 ref={headingRef} tabIndex={-1} className="text-sm font-semibold text-ink">
            {step.title}
          </h2>
          <p id={bodyId} className="text-sm text-muted">
            {step.body}
          </p>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={state.stepIndex === 0}
              onClick={handleBack}
            >
              Tour back
            </Button>
            <Button size="sm" onClick={handleNext}>
              Tour next
            </Button>
            <Button size="sm" variant="ghost" className="ml-auto" onClick={skip}>
              Skip tour
            </Button>
          </div>
          <div className="flex justify-end">
            <Button size="sm" variant="ghost" onClick={restart}>
              Restart tour
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
