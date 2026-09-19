import type { TrendPoint } from "../../api";
import { cx } from "../ui";

export interface TrendChartProps {
  points: TrendPoint[];
  /** Accessible description of what is being charted. */
  subject?: string;
}

const POINT_WIDTH = 64;
const PLOT_HEIGHT = 110;
const PAD_TOP = 20;
const PAD_BOTTOM = 30;
const BAR_WIDTH = 26;

/**
 * Labeled SVG bar chart of server-provided trend points. Only points the
 * server returned are rendered — missing dates are never filled with zeros.
 */
export function TrendChart({ points, subject = "Fail and error findings" }: TrendChartProps) {
  if (points.length === 0) {
    return null;
  }
  const totals = points.map((point) => point.fail_finding_count + point.error_finding_count);
  const max = totals.reduce((runningMax, value) => Math.max(runningMax, value), 0);
  const width = points.length * POINT_WIDTH;
  const baseline = PAD_TOP + PLOT_HEIGHT;
  const firstDate = points[0]?.date ?? "";
  const lastDate = points[points.length - 1]?.date ?? "";

  return (
    <figure className="grid gap-2">
      <svg
        role="img"
        aria-label={`${subject}: daily points from ${firstDate} to ${lastDate} across the ${points.length} days the server returned`}
        viewBox={`0 0 ${width} ${baseline + PAD_BOTTOM}`}
        className="w-full"
      >
        <line x1="0" y1={baseline} x2={width} y2={baseline} className="stroke-line" strokeWidth="1" />
        {points.map((point, index) => {
          const slotStart = index * POINT_WIDTH + (POINT_WIDTH - BAR_WIDTH) / 2;
          const center = slotStart + BAR_WIDTH / 2;
          const failHeight = scaledHeight(point.fail_finding_count, max);
          const errorHeight = scaledHeight(point.error_finding_count, max);
          const failY = baseline - failHeight;
          const errorY = failY - errorHeight;
          const total = point.fail_finding_count + point.error_finding_count;
          return (
            <g key={point.date}>
              {total > 0 && (
                <text
                  x={center}
                  y={errorY - 6}
                  textAnchor="middle"
                  className="fill-muted text-[10px] tabular-nums"
                >
                  {total}
                </text>
              )}
              {failHeight > 0 && (
                <rect x={slotStart} y={failY} width={BAR_WIDTH} height={failHeight} rx="2" className="fill-fail/80" />
              )}
              {errorHeight > 0 && (
                <rect x={slotStart} y={errorY} width={BAR_WIDTH} height={errorHeight} rx="2" className="fill-error/80" />
              )}
              <text x={center} y={baseline + 18} textAnchor="middle" className="fill-muted text-[10px] tabular-nums">
                {point.date}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="flex items-center gap-4 text-xs text-muted">
        <LegendSwatch className="bg-fail/80" label="Fail findings" />
        <LegendSwatch className="bg-error/80" label="Error findings" />
      </figcaption>
    </figure>
  );
}

function scaledHeight(value: number, max: number): number {
  if (max <= 0 || value <= 0) {
    return 0;
  }
  // Minimum 2px so nonzero values stay visible; zero values get no bar at all.
  return Math.max(2, (value / max) * PLOT_HEIGHT);
}

function LegendSwatch({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden="true" className={cx("h-2 w-2 rounded-sm", className)} />
      {label}
    </span>
  );
}
