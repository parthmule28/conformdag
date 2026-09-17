/**
 * Runtime observations retained in the canonical report, shown verbatim as
 * formatted JSON. There is nothing to derive: an absent list renders a calm
 * empty state.
 */
import { EmptyState } from "../ui";

export function RuntimeObservations({
  observations,
}: {
  observations: Record<string, unknown>[];
}) {
  if (observations.length === 0) {
    return (
      <EmptyState
        title="No runtime observations"
        description="The scan retained no runtime observations."
      />
    );
  }
  return (
    <ul className="grid gap-2" aria-label="Runtime observations">
      {observations.map((observation, index) => (
        <li key={index}>
          <pre className="overflow-x-auto rounded-sm border border-line bg-sunken p-2 font-mono text-xs text-ink">
            {JSON.stringify(observation, null, 2)}
          </pre>
        </li>
      ))}
    </ul>
  );
}
