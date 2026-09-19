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
    <section className={cx("rounded-lg border border-line bg-raised shadow-card", className)}>
      {(title !== undefined || actions !== undefined) && (
        <header className="flex items-start justify-between gap-4 border-b border-line px-4 py-3.5 sm:px-5">
          <div className="min-w-0">
            {title !== undefined && <h2 className="text-base font-semibold tracking-tight text-ink">{title}</h2>}
            {subtitle !== undefined && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {actions !== undefined && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4 sm:p-5">{children}</div>
      {footer !== undefined && (
        <footer className="border-t border-line px-4 py-3.5 text-sm text-muted sm:px-5">{footer}</footer>
      )}
    </section>
  );
}
