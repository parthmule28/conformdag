import type { PackSummary } from "../../api";
import { StatusBadge, cx } from "../ui";

export interface PackListProps {
  packs: PackSummary[];
  selected: string | null;
  onSelect: (packName: string) => void;
}

/**
 * Selectable policy-pack sections. Each row is a toggle button linking the
 * pack summary (version, policy count, server-reported validation state) to
 * the pack's policy and gate views.
 */
export function PackList({ packs, selected, onSelect }: PackListProps) {
  return (
    <ul className="grid gap-2">
      {packs.map((pack) => {
        const active = pack.name === selected;
        return (
          <li key={pack.name}>
            <button
              type="button"
              aria-pressed={active}
              data-tour="policy-pack"
              onClick={() => onSelect(pack.name)}
              className={cx(
                "grid w-full gap-1 rounded-sm border px-3 py-2 text-left transition-colors",
                active ? "border-accent bg-accent/5" : "border-line bg-raised hover:bg-sunken",
              )}
            >
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-ink">{pack.name}</span>
                {pack.error === null ? <StatusBadge status="PASS" /> : <StatusBadge status="ERROR" />}
              </span>
              <span className="text-xs text-muted">
                Version {pack.version ?? "unknown"} &middot; {pack.policy_count}{" "}
                {pack.policy_count === 1 ? "policy" : "policies"}
              </span>
              {pack.error !== null && (
                <span className="text-xs font-medium text-fail">{pack.error}</span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
