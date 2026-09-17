import { Button, cx } from "./Button";

export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  className?: string;
}

export function Pagination({ page, pageSize, total, onPageChange, className }: PaginationProps) {
  const safePageSize = Math.max(1, pageSize);
  const pageCount = Math.max(1, Math.ceil(total / safePageSize));
  const current = Math.min(Math.max(1, page), pageCount);
  const firstItem = total === 0 ? 0 : (current - 1) * safePageSize + 1;
  const lastItem = Math.min(total, current * safePageSize);

  return (
    <nav
      aria-label="Pagination"
      className={cx("flex flex-wrap items-center justify-between gap-2 text-sm text-muted", className)}
    >
      <span aria-live="polite">
        {total === 0 ? "No items" : `Showing ${firstItem}\u2013${lastItem} of ${total}`}
      </span>
      <div className="flex items-center gap-1">
        <Button
          variant="secondary"
          size="sm"
          disabled={current <= 1}
          onClick={() => onPageChange(current - 1)}
        >
          Previous
        </Button>
        <span className="px-1.5 tabular-nums">
          Page {current} of {pageCount}
        </span>
        <Button
          variant="secondary"
          size="sm"
          disabled={current >= pageCount}
          onClick={() => onPageChange(current + 1)}
        >
          Next
        </Button>
      </div>
    </nav>
  );
}
