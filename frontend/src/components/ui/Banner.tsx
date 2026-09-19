import type { ReactNode } from "react";

import { cx, IconButton } from "./Button";

export type BannerVariant = "info" | "success" | "warning" | "error";

const VARIANT_CLASSES: Record<BannerVariant, string> = {
  info: "border-line bg-raised text-ink",
  success: "border-pass/40 bg-pass/10 text-ink",
  warning: "border-warning/50 bg-warning/10 text-ink",
  error: "border-fail/50 bg-fail/10 text-ink",
};

const ICON_CLASSES: Record<BannerVariant, string> = {
  info: "text-muted",
  success: "text-pass",
  warning: "text-warning",
  error: "text-fail",
};

interface IconProps {
  viewBox: string;
  className: string;
  fill: string;
  stroke: string;
  strokeWidth: number;
}

const ICON_PROPS: IconProps = {
  viewBox: "0 0 16 16",
  className: "h-4 w-4",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
};

function BannerIcon({ variant }: { variant: BannerVariant }) {
  switch (variant) {
    case "info":
      return (
        <svg {...ICON_PROPS}>
          <circle cx="8" cy="8" r="6.5" />
          <path d="M8 7.5v3.5" />
          <path d="M8 5.2h.01" strokeLinecap="round" />
        </svg>
      );
    case "success":
      return (
        <svg {...ICON_PROPS}>
          <path d="M13.5 8a5.5 5.5 0 1 1-2.1-4.33" />
          <path d="M6.3 7.7l2 2 5-5.4" />
        </svg>
      );
    case "warning":
      return (
        <svg {...ICON_PROPS}>
          <path d="M8 2.5 14.5 13.5h-13L8 2.5Z" />
          <path d="M8 6.8v2.9" />
          <path d="M8 11.9h.01" strokeLinecap="round" />
        </svg>
      );
    case "error":
      return (
        <svg {...ICON_PROPS}>
          <path d="M5.7 2.5h4.6l3.2 3.2v4.6l-3.2 3.2H5.7l-3.2-3.2V5.7l3.2-3.2Z" />
          <path d="M8 5.5v3" />
          <path d="M8 10.6h.01" strokeLinecap="round" />
        </svg>
      );
  }
}

export interface BannerProps {
  variant?: BannerVariant;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  onDismiss?: () => void;
  className?: string;
}

export function Banner({ variant = "info", title, children, action, onDismiss, className }: BannerProps) {
  return (
    <div
      role={variant === "error" || variant === "warning" ? "alert" : "status"}
      className={cx(
        "flex items-start gap-2.5 rounded-md border px-3 py-2.5 text-sm",
        VARIANT_CLASSES[variant],
        className,
      )}
    >
      <span aria-hidden="true" className={cx("mt-0.5 shrink-0", ICON_CLASSES[variant])}>
        <BannerIcon variant={variant} />
      </span>
      <div className="min-w-0 flex-1">
        {title !== undefined && <p className="font-semibold">{title}</p>}
        {children !== undefined && <div className={cx(title !== undefined && "mt-0.5")}>{children}</div>}
      </div>
      {action !== undefined && <div className="shrink-0">{action}</div>}
      {onDismiss !== undefined && (
        <IconButton label="Dismiss" onClick={onDismiss} className="-m-1 border-transparent bg-transparent">
          <span aria-hidden="true">&times;</span>
        </IconButton>
      )}
    </div>
  );
}
