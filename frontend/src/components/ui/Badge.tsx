import { cx } from "./Button";

export const STATUSES = ["PASS", "FAIL", "ERROR", "INCOMPLETE", "SUPPRESSED", "NOT EVALUATED"] as const;

export type Status = (typeof STATUSES)[number];

const STATUS_CLASSES: Record<Status, string> = {
  PASS: "border-pass/40 bg-pass/10 text-pass",
  FAIL: "border-fail/40 bg-fail/10 text-fail",
  ERROR: "border-error/40 bg-error/10 text-error",
  INCOMPLETE: "border-warning/40 bg-warning/10 text-warning",
  SUPPRESSED: "border-suppressed/40 bg-suppressed/10 text-suppressed",
  "NOT EVALUATED": "border-line bg-sunken text-muted",
};

const STATUS_DOT_CLASSES: Record<Status, string> = {
  PASS: "bg-pass",
  FAIL: "bg-fail",
  ERROR: "bg-error",
  INCOMPLETE: "bg-warning",
  SUPPRESSED: "bg-suppressed",
  "NOT EVALUATED": "bg-neutral",
};

export interface StatusBadgeProps {
  status: Status;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-1 text-xs font-semibold tracking-wide",
        STATUS_CLASSES[status],
        className,
      )}
    >
      <span aria-hidden="true" className={cx("h-1.5 w-1.5 rounded-full", STATUS_DOT_CLASSES[status])} />
      {status}
    </span>
  );
}
