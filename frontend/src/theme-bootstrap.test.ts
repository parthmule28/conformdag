import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const indexHtml = readFileSync(resolve(process.cwd(), "index.html"), "utf8");

describe("theme bootstrap", () => {
  it("applies a stored theme before the application module can paint", () => {
    const bootstrapIndex = indexHtml.indexOf("conformdag-theme");
    const moduleIndex = indexHtml.indexOf('<script type="module"');

    expect(bootstrapIndex).toBeGreaterThanOrEqual(0);
    expect(indexHtml.slice(0, moduleIndex)).toContain("data-theme");
    expect(bootstrapIndex).toBeLessThan(moduleIndex);
  });
});
