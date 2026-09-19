import type { ComponentPropsWithoutRef, ReactNode } from "react";

import { cx } from "./Button";
import { EmptyState } from "./EmptyState";

export interface TableProps {
  caption: string;
  empty?: boolean;
  emptyMessage?: string;
  className?: string;
  children: ReactNode;
}

export function Table({ caption, empty = false, emptyMessage = "Nothing to show yet.", className, children }: TableProps) {
  if (empty) {
    return <EmptyState title={caption} description={emptyMessage} />;
  }
  return (
    <div className={cx("overflow-x-auto rounded-md border border-line bg-raised", className)}>
      <table className="w-full min-w-[40rem] border-collapse text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  );
}

export function Th({ className, ...rest }: ComponentPropsWithoutRef<"th">) {
  return (
    <th
      scope="col"
      className={cx(
        "border-b border-line px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted",
        className,
      )}
      {...rest}
    />
  );
}

export function Td({ className, ...rest }: ComponentPropsWithoutRef<"td">) {
  return <td className={cx("border-b border-line px-3 py-2 align-top text-ink", className)} {...rest} />;
}
