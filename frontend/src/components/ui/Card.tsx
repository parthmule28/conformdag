import type { ReactNode } from "react";

import { cx } from "./Button";

export interface CardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  className?: string;
  children?: ReactNode;
}

export function Card({ title, subtitle, actions, footer, className, children }: CardProps) {
  return (
    <section className={cx("rounded-md border border-line bg-raised shadow-card", className)}>
      {(title !== undefined || actions !== undefined) && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0">
            {title !== undefined && <h2 className="text-base font-semibold text-ink">{title}</h2>}
            {subtitle !== undefined && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {actions !== undefined && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
      {footer !== undefined && (
        <footer className="border-t border-line px-4 py-3 text-sm text-muted">{footer}</footer>
      )}
    </section>
  );
}
