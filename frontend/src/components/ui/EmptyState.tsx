import type { ReactNode } from "react";

import { cx } from "./Button";

export interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cx(
        "flex flex-col items-center gap-1.5 rounded-md border border-dashed border-line bg-raised px-6 py-10 text-center",
        className,
      )}
    >
      <p className="text-sm font-semibold text-ink">{title}</p>
      {description !== undefined && <p className="max-w-md text-sm text-muted">{description}</p>}
      {action !== undefined && <div className="mt-2">{action}</div>}
    </div>
  );
}
