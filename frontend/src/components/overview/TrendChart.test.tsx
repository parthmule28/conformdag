import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TrendChart } from "./TrendChart";

const BASE_POINT = {
  date: "2026-09-16",
  completed_scan_count: 2,
  fail_finding_count: 2,
  error_finding_count: 1,
  suppressed_finding_count: 1,
  new_finding_count: 3,
};

const POINTS = [
  BASE_POINT,
  {
    date: "2026-09-17",
    completed_scan_count: 1,
    fail_finding_count: 0,
    error_finding_count: 0,
    suppressed_finding_count: 0,
    new_finding_count: 0,
  },
];

const MANY_POINTS = Array.from({ length: 10 }, (_, index) => ({
  ...BASE_POINT,
  date: `2026-09-${String(index + 16).padStart(2, "0")}`,
}));

const PEAK_OF_FIVE = [
  {
    date: "2026-09-16",
    completed_scan_count: 1,
    fail_finding_count: 3,
    error_finding_count: 2,
    suppressed_finding_count: 0,
    new_finding_count: 0,
  },
];

afterEach(cleanup);

describe("TrendChart", () => {
  it("gives the chart a descriptive accessible name and a readable summary", () => {
    render(<TrendChart points={POINTS} />);

    expect(screen.getByRole("img", { name: /Finding volume by day.*daily points from/ })).toHaveClass("h-64");
    expect(screen.getByText(/2 days.*3 findings total.*peak 3 on Sep 16/i)).toBeInTheDocument();
    expect(screen.getAllByText("Sep 16").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Sep 17").length).toBeGreaterThan(0);
  });

  it("provides an accessible trend data table alongside the visual chart", () => {
    render(<TrendChart points={POINTS} />);

    fireEvent.click(screen.getByText("View trend data"));

    const table = screen.getByRole("table", { name: "Trend data" });
    expect(within(table).getByRole("columnheader", { name: "Date" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Fail findings" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "Sep 16" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: /^2$/ })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: /^1$/ })).toBeInTheDocument();
  });

  it("keeps enough intrinsic width for multi-day charts to scroll on narrow screens", () => {
    render(<TrendChart points={MANY_POINTS} />);

    expect(screen.getByRole("img", { name: /Finding volume by day.*daily points from/ })).toHaveStyle({
      width: "max(100%, 756px)",
    });
  });

  it("labels the y-axis with the true midpoint, keeping 0 and max endpoints", () => {
    const { container } = render(<TrendChart points={PEAK_OF_FIVE} />);

    const tickLabels = Array.from(container.querySelectorAll("svg text[x='0']")).map(
      (node) => node.textContent,
    );
    expect(tickLabels).toEqual(["5", "2.5", "0"]);
  });
});
