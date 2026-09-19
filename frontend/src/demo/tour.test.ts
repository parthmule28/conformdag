import { describe, expect, it } from "vitest";

import { isDemoTourEnabled, reduceTour, toDemoLocation } from "./tour";

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
    expect(toDemoLocation("/repos/repo-1", "?demo=1")).toBe("/repos/repo-1?demo=1");
    expect(toDemoLocation("/policies", "?demo=1&mode=compact")).toBe(
      "/policies?demo=1&mode=compact",
    );
  });

  it("supports restart and bounded back/next transitions", () => {
    expect(reduceTour({ index: 0, dismissed: false }, { type: "next", count: 3 })).toEqual({
      index: 1,
      dismissed: false,
    });
    expect(reduceTour({ index: 1, dismissed: false }, { type: "back", count: 3 })).toEqual({
      index: 0,
      dismissed: false,
    });
    expect(reduceTour({ index: 2, dismissed: false }, { type: "next", count: 3 })).toEqual({
      index: 2,
      dismissed: false,
    });
    expect(reduceTour({ index: 2, dismissed: true }, { type: "restart", count: 3 })).toEqual({
      index: 0,
      dismissed: false,
    });
  });
});
