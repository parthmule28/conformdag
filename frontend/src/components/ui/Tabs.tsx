import type { ComponentPropsWithoutRef, KeyboardEvent } from "react";

import { cx } from "./Button";

export interface TabItem {
  id: string;
  label: string;
}

export interface TabsProps {
  tabs: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  label?: string;
  className?: string;
}

export function Tabs({ tabs, activeId, onChange, label = "Sections", className }: TabsProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>): void => {
    const ids = tabs.map((tab) => tab.id);
    const currentIndex = ids.indexOf(activeId);
    if (currentIndex === -1) {
      return;
    }
    let nextIndex: number;
    switch (event.key) {
      case "ArrowRight":
        nextIndex = (currentIndex + 1) % ids.length;
        break;
      case "ArrowLeft":
        nextIndex = (currentIndex - 1 + ids.length) % ids.length;
        break;
      case "Home":
        nextIndex = 0;
        break;
      case "End":
        nextIndex = ids.length - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    const nextId = ids[nextIndex];
    if (nextId === undefined) {
      return;
    }
    onChange(nextId);
    document.getElementById(`conformdag-tab-${nextId}`)?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      className={cx("flex items-center gap-1 border-b border-line", className)}
    >
      {tabs.map((tab) => {
        const active = tab.id === activeId;
        return (
          <button
            key={tab.id}
            id={`conformdag-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={active}
            aria-controls={`conformdag-panel-${tab.id}`}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={handleKeyDown}
            className={cx(
              "-mb-px rounded-sm border-b-2 px-2.5 py-1.5 text-sm font-medium transition-colors",
              active ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export interface TabPanelProps extends ComponentPropsWithoutRef<"div"> {
  tabId: string;
  active: boolean;
}

export function TabPanel({ tabId, active, className, children, ...rest }: TabPanelProps) {
  if (!active) {
    return null;
  }
  return (
    <div
      role="tabpanel"
      id={`conformdag-panel-${tabId}`}
      aria-labelledby={`conformdag-tab-${tabId}`}
      tabIndex={0}
      className={cx("py-3 focus:outline-none", className)}
      {...rest}
    >
      {children}
    </div>
  );
}
