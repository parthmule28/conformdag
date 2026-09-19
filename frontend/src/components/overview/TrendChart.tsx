import { useId } from "react";

import type { TrendPoint } from "../../api";
import { cx } from "../ui";

export interface TrendChartProps {
  points: TrendPoint[];
  /** Accessible description of what is being charted. */
  subject?: string;
}

const POINT_WIDTH = 72;
const PLOT_HEIGHT = 150;
const PAD_TOP = 24;
const PAD_BOTTOM = 38;
const CHART_LEFT = 36;
const BAR_WIDTH = 32;

const DATE_FORMATTER = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

/**
 * Labeled SVG bar chart of server-provided trend points. Only points the
 * server returned are rendered — missing dates are never filled with zeros.
 */
export function TrendChart({ points, subject = "Fail and error findings" }: TrendChartProps) {
  const chartId = useId().replaceAll(":", "");

  if (points.length === 0) {
    return null;
  }

  const totals = points.map((point) => point.fail_finding_count + point.error_finding_count);
  const max = totals.reduce((runningMax, value) => Math.max(runningMax, value), 0);
  const scaleMax = Math.max(max, 1);
  const width = CHART_LEFT + points.length * POINT_WIDTH;
  const baseline = PAD_TOP + PLOT_HEIGHT;
  const firstDate = points[0]?.date ?? "";
  const lastDate = points[points.length - 1]?.date ?? "";
  const peakIndex = totals.reduce(
    (bestIndex, value, index) => (value > (totals[bestIndex] ?? 0) ? index : bestIndex),
    0,
  );
  const peak = totals[peakIndex] ?? 0;
  const peakDate = formatTrendDate(points[peakIndex]?.date ?? "");
  const totalFindings = totals.reduce((sum, value) => sum + value, 0);
  const dayLabel = points.length === 1 ? "day" : "days";
  const summary = `${points.length} ${dayLabel} · ${totalFindings} findings total · peak ${peak} on ${peakDate}`;
  const chartWidth = Math.max(width, 448);
  const chartTitleId = `${chartId}-title`;
  const chartDescriptionId = `${chartId}-description`;
  const errorPatternId = `${chartId}-error-pattern`;
  const chartLabel = `Finding volume by day: ${subject}, daily points from ${firstDate} to ${lastDate} across the ${points.length} ${dayLabel} the server returned`;
  const ticks = tickValues(scaleMax);

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-sm font-semibold text-ink">Finding volume by day</p>
        <p className="text-xs tabular-nums text-muted">{summary}</p>
      </div>
      <figure className="grid gap-3">
        <div className="overflow-x-auto pb-1">
          <svg
            role="img"
            aria-labelledby={chartTitleId}
            aria-describedby={chartDescriptionId}
            viewBox={`0 0 ${width} ${baseline + PAD_BOTTOM}`}
            className="h-64"
            style={{ width: `max(100%, ${chartWidth}px)` }}
          >
            <title id={chartTitleId}>{chartLabel}</title>
            <desc id={chartDescriptionId}>
              {subject}: daily points from {firstDate} to {lastDate} across the {points.length} days the server returned.
            </desc>
            <defs>
              <pattern id={errorPatternId} width="6" height="6" patternUnits="userSpaceOnUse">
                <rect width="6" height="6" className="fill-error" />
                <path d="M-1 1L1 -1M0 6L6 0M5 7L7 5" stroke="var(--surface-raised)" strokeWidth="1" />
              </pattern>
            </defs>
            {ticks.map((tick) => {
              const y = baseline - (tick / scaleMax) * PLOT_HEIGHT;
              return (
                <g key={tick} aria-hidden="true">
                  <line
                    x1={CHART_LEFT}
                    y1={y}
                    x2={width}
                    y2={y}
                    className="stroke-line"
                    strokeWidth="1"
                    strokeDasharray={tick === 0 ? undefined : "3 4"}
                  />
                  <text x={0} y={y + 4} className="fill-muted text-[10px] tabular-nums">
                    {tick}
                  </text>
                </g>
              );
            })}
            {points.map((point, index) => {
              const slotStart = CHART_LEFT + index * POINT_WIDTH + (POINT_WIDTH - BAR_WIDTH) / 2;
              const center = slotStart + BAR_WIDTH / 2;
              const failHeight = scaledHeight(point.fail_finding_count, scaleMax);
              const errorHeight = scaledHeight(point.error_finding_count, scaleMax);
              const failY = baseline - failHeight;
              const errorY = failY - errorHeight;
              const total = point.fail_finding_count + point.error_finding_count;
              const formattedDate = formatTrendDate(point.date);
              return (
                <g key={point.date}>
                  <title>
                    {formattedDate}: {total} total findings; {point.fail_finding_count} fail; {point.error_finding_count} error
                  </title>
                  {total > 0 && (
                    <text
                      x={center}
                      y={errorY - 8}
                      textAnchor="middle"
                      className="fill-ink text-[11px] font-semibold tabular-nums"
                    >
                      {total}
                    </text>
                  )}
                  {failHeight > 0 && (
                    <rect
                      x={slotStart}
                      y={failY}
                      width={BAR_WIDTH}
                      height={failHeight}
                      rx="3"
                      className="fill-fail"
                    />
                  )}
                  {errorHeight > 0 && (
                    <rect
                      x={slotStart}
                      y={errorY}
                      width={BAR_WIDTH}
                      height={errorHeight}
                      rx="3"
                      fill={`url(#${errorPatternId})`}
                    />
                  )}
                  <text
                    x={center}
                    y={baseline + 22}
                    textAnchor="middle"
                    className="fill-muted text-[11px] tabular-nums"
                  >
                    {formattedDate}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
        <figcaption className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
          <LegendSwatch className="bg-fail" label="Fail findings" />
          <LegendSwatch className="trend-error-swatch" label="Error findings" />
        </figcaption>
      </figure>
      <details className="rounded-md border border-line bg-surface">
        <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-ink transition-colors hover:bg-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
          View trend data
        </summary>
        <div className="overflow-x-auto border-t border-line">
          <table className="w-full min-w-[32rem] border-collapse text-left text-sm" aria-label="Trend data">
            <caption className="sr-only">Trend data</caption>
            <thead>
              <tr>
                <th scope="col" className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
                  Date
                </th>
                <th scope="col" className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
                  Total findings
                </th>
                <th scope="col" className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
                  Fail findings
                </th>
                <th scope="col" className="border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
                  Error findings
                </th>
              </tr>
            </thead>
            <tbody>
              {points.map((point) => (
                <tr key={point.date}>
                  <td className="border-b border-line px-3 py-2 font-medium text-ink">{formatTrendDate(point.date)}</td>
                  <td className="border-b border-line px-3 py-2 tabular-nums text-ink">
                    {point.fail_finding_count + point.error_finding_count}
                  </td>
                  <td className="border-b border-line px-3 py-2 tabular-nums text-ink">{point.fail_finding_count}</td>
                  <td className="border-b border-line px-3 py-2 tabular-nums text-ink">{point.error_finding_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

function scaledHeight(value: number, max: number): number {
  if (max <= 0 || value <= 0) {
    return 0;
  }
  // Minimum 2px so nonzero values stay visible; zero values get no bar at all.
  return Math.max(2, (value / max) * PLOT_HEIGHT);
}

function tickValues(max: number): number[] {
  // Finding counts are integers: prefer a readable whole-number midpoint
  // (5 → 2, 4 → 2) and remove duplicates for very small scales.
  const midpoint = Math.floor(max / 2);
  return [...new Set([max, midpoint, 0])];
}

function formatTrendDate(value: string): string {
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.valueOf()) ? value : DATE_FORMATTER.format(date);
}

function LegendSwatch({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden="true" className={cx("h-2 w-2 rounded-sm", className)} />
      {label}
    </span>
  );
}
