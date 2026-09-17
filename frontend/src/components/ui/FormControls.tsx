import { useId, type ComponentPropsWithoutRef, type ReactNode } from "react";

import { cx } from "./Button";

const FIELD_CLASSES =
  "w-full rounded-sm border bg-raised px-2.5 py-1.5 text-sm text-ink placeholder:text-muted/70 disabled:cursor-not-allowed disabled:opacity-50";

interface FieldShellProps {
  id: string;
  label: string;
  hint?: string;
  hintId: string;
  error?: string;
  errorId: string;
  children: ReactNode;
}

function FieldShell({ id, label, hint, hintId, error, errorId, children }: FieldShellProps) {
  return (
    <div className="grid gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {hint !== undefined && (
        <p id={hintId} className="text-xs text-muted">
          {hint}
        </p>
      )}
      {children}
      {error !== undefined && (
        <p id={errorId} className="text-xs font-medium text-fail">
          {error}
        </p>
      )}
    </div>
  );
}

interface FieldExtras {
  label: string;
  hint?: string;
  error?: string;
}

function fieldAria(inputId: string, extras: FieldExtras): {
  hintId: string;
  errorId: string;
  describedBy: string | undefined;
} {
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const describedBy = [
    extras.hint !== undefined ? hintId : null,
    extras.error !== undefined ? errorId : null,
  ]
    .filter(Boolean)
    .join(" ");
  return { hintId, errorId, describedBy: describedBy === "" ? undefined : describedBy };
}

export interface InputProps extends ComponentPropsWithoutRef<"input">, FieldExtras {}

export function Input({ label, hint, error, id, className, ...rest }: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const { hintId, errorId, describedBy } = fieldAria(inputId, { label, hint, error });
  return (
    <FieldShell id={inputId} label={label} hint={hint} hintId={hintId} error={error} errorId={errorId}>
      <input
        id={inputId}
        aria-invalid={error !== undefined || undefined}
        aria-describedby={describedBy}
        className={cx(FIELD_CLASSES, error !== undefined ? "border-fail" : "border-line", className)}
        {...rest}
      />
    </FieldShell>
  );
}

export interface SelectProps extends ComponentPropsWithoutRef<"select">, FieldExtras {}

export function Select({ label, hint, error, id, className, children, ...rest }: SelectProps) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const { hintId, errorId, describedBy } = fieldAria(selectId, { label, hint, error });
  return (
    <FieldShell id={selectId} label={label} hint={hint} hintId={hintId} error={error} errorId={errorId}>
      <select
        id={selectId}
        aria-invalid={error !== undefined || undefined}
        aria-describedby={describedBy}
        className={cx(FIELD_CLASSES, error !== undefined ? "border-fail" : "border-line", className)}
        {...rest}
      >
        {children}
      </select>
    </FieldShell>
  );
}

export interface TextareaProps extends ComponentPropsWithoutRef<"textarea">, FieldExtras {}

export function Textarea({ label, hint, error, id, className, rows = 3, ...rest }: TextareaProps) {
  const generatedId = useId();
  const textareaId = id ?? generatedId;
  const { hintId, errorId, describedBy } = fieldAria(textareaId, { label, hint, error });
  return (
    <FieldShell id={textareaId} label={label} hint={hint} hintId={hintId} error={error} errorId={errorId}>
      <textarea
        id={textareaId}
        rows={rows}
        aria-invalid={error !== undefined || undefined}
        aria-describedby={describedBy}
        className={cx(FIELD_CLASSES, error !== undefined ? "border-fail" : "border-line", className)}
        {...rest}
      />
    </FieldShell>
  );
}
