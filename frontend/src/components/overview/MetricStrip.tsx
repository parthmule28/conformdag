import { cx } from "../ui";

export type MetricTone = "neutral" | "accent" | "fail" | "error";

export interface MetricItem {
  label: string;
  value: number;
  tone?: MetricTone;
}

const VALUE_CLASSES: Record<MetricTone, string> = {
  neutral: "text-ink",
  accent: "text-accent",
  fail: "text-fail",
  error: "text-error",
};

export interface MetricStripProps {
  metrics: MetricItem[];
  className?: string;
}

export function MetricStrip({ metrics, className }: MetricStripProps) {
  return (
    <dl className={cx("grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6", className)}>
      {metrics.map((metric) => (
        <div
          key={metric.label}
          className="rounded-md border border-line bg-raised px-3 py-2.5 shadow-card"
        >
          <dt className="text-xs font-medium uppercase tracking-wide text-muted">{metric.label}</dt>
          <dd
            className={cx(
              "mt-1 text-2xl font-semibold tabular-nums",
              VALUE_CLASSES[metric.tone ?? "neutral"],
            )}
          >
            {metric.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
