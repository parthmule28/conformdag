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
    <dl className={cx("grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6", className)}>
      {metrics.map((metric) => (
        <div
          key={metric.label}
          className="rounded-lg border border-line bg-raised px-3.5 py-3 shadow-card transition-colors hover:border-accent/40"
        >
          <dt className="text-[0.6875rem] font-semibold uppercase tracking-[0.08em] text-muted">{metric.label}</dt>
          <dd
            className={cx(
              "mt-1.5 text-2xl font-semibold leading-none tabular-nums",
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
