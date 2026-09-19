import { describe, expect, it } from "vitest";

describe("React test environment", () => {
  it("enables the real act environment contract", () => {
    expect((globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT).toBe(true);
  });
});
