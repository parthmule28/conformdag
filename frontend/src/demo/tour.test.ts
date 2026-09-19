import { describe, expect, it } from "vitest";

import { isDemoTourEnabled, initialTourState, toDemoLocation, tourReducer } from "./tour";

describe("demo tour route state", () => {
  it.each(["", "?demo=", "?demo=0", "?demo=true", "?other=1"]) (
    "does not activate for %s",
    (search) => {
      expect(isDemoTourEnabled(search)).toBe(false);
    },
  );

  it("activates only for the exact demo=1 query value", () => {
    expect(isDemoTourEnabled("?demo=1")).toBe(true);
    expect(isDemoTourEnabled("?demo=1&mode=compact")).toBe(true);
  });

  it("preserves demo activation when tour navigation changes routes", () => {
    expect(toDemoLocation("/repos/repo-1", "?demo=1")).toEqual({
      pathname: "/repos/repo-1",
      search: "?demo=1",
    });
    expect(toDemoLocation("/policies", "?demo=1&mode=compact")).toEqual({
      pathname: "/policies",
      search: "?demo=1&mode=compact",
    });
  });

  it("supports restart and bounded back/next transitions", () => {
    const initial = initialTourState();
    const next = tourReducer(initial, { type: "next", route: "/repos/repo-1?demo=1" });
    expect(next.stepIndex).toBe(1);
    const back = tourReducer(next, { type: "back" });
    expect(back.stepIndex).toBe(0);
    const finish = tourReducer(back, { type: "finish" });
    expect(finish.dismissed).toBe(true);
    expect(tourReducer(finish, { type: "restart" })).toMatchObject({
      stepIndex: 0,
      dismissed: false,
    });
  });
});
