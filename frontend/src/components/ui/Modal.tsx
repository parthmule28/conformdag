import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { IconButton } from "./Button";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function Modal({ open, onClose, title, children, footer }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  const titleId = useId();

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    restoreFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // Initial focus goes to the dialog panel itself (tabIndex={-1}), not the
    // first focusable element: the header's dismiss control precedes the
    // content in the DOM and must not absorb the opening focus.
    panelRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const currentPanel = panelRef.current;
      if (currentPanel === null) {
        return;
      }
      const focusable = Array.from(currentPanel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusable.length === 0) {
        event.preventDefault();
        currentPanel.focus();
        return;
      }
      const firstElement = focusable[0];
      const lastElement = focusable[focusable.length - 1];
      if (firstElement === undefined || lastElement === undefined) {
        return;
      }
      const active = document.activeElement;
      const insidePanel = active !== null && currentPanel.contains(active);
      if (event.shiftKey && (active === firstElement || !insidePanel)) {
        event.preventDefault();
        lastElement.focus();
        return;
      }
      if (!event.shiftKey && (active === lastElement || !insidePanel)) {
        event.preventDefault();
        firstElement.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      restoreFocusRef.current?.focus();
      restoreFocusRef.current = null;
    };
  }, [open]);

  if (!open) {
    return null;
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="w-full max-w-lg rounded-md border border-line bg-raised shadow-overlay focus:outline-none"
      >
        <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
          <h2 id={titleId} className="text-base font-semibold text-ink">
            {title}
          </h2>
          <IconButton label="Close" onClick={onClose}>
            <span aria-hidden="true">&times;</span>
          </IconButton>
        </header>
        <div className="max-h-[70vh] overflow-y-auto px-4 py-3 text-sm">{children}</div>
        {footer !== undefined && (
          <footer className="flex items-center justify-end gap-2 border-t border-line px-4 py-3">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body,
  );
}
