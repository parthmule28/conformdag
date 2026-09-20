import { useState, type FormEvent } from "react";

import type { PolicyConfiguration, PolicyInfo, PolicyUpsertRequest } from "../../api";
import {
  describeApiError,
  useUpdatePolicyMutation,
} from "../../hooks/usePlatformQueries";
import { Banner, Button, Input, Modal, Select, Textarea } from "../ui";

const LIFECYCLE_STATUSES = [
  "DRAFT",
  "APPROVED",
  "ACTIVE",
  "CONFLICTED",
  "DEPRECATED",
  "REJECTED",
] as const;

const SEVERITIES = ["info", "low", "medium", "high", "critical"] as const;

interface PolicyDraft {
  title: string;
  version: string;
  status: string;
  severity: string;
  invariant: string;
  tagsText: string;
  deterministicChecksText: string;
  configurationText: string;
  sourceDocument: string;
  sourceSection: string;
  sourceVersion: string;
  safePath: string;
}

function draftFromPolicy(policy: PolicyInfo): PolicyDraft {
  return {
    title: policy.title,
    version: policy.version,
    status: policy.status,
    severity: policy.severity,
    invariant: policy.invariant,
    tagsText: policy.tags.join(", "),
    deterministicChecksText: policy.deterministic_checks.join(", "),
    configurationText: JSON.stringify(policy.configuration, null, 2),
    sourceDocument: policy.source_document,
    sourceSection: policy.source_section,
    sourceVersion: policy.source_version ?? "",
    safePath: policy.safe_path ?? "",
  };
}

function parseTags(tagsText: string): string[] {
  return tagsText
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag !== "");
}

/**
 * Parses the configuration JSON draft. Parse errors are returned as a
 * form error so a broken draft stays in the editor and can never be saved.
 */
function parseConfiguration(text: string): { configuration: Record<string, unknown> | null; error: string | null } {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { configuration: null, error: "Configuration must be valid JSON." };
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { configuration: null, error: "Configuration must be a JSON object." };
  }
  return { configuration: parsed as Record<string, unknown>, error: null };
}

export interface PolicyEditorProps {
  packName: string;
  policy: PolicyInfo;
  onClose: () => void;
}

/**
 * Modal editor for one existing policy. The payload always carries the
 * loaded contract metadata (ownership, scope, and exceptions) untouched, and
 * synchronizes the nested enforcement check list with the canonical field so
 * an edit remains lossless; tags travel as an explicit ordered list (including
 * `[]` when cleared). Server rejections keep the draft open.
 */
export function PolicyEditor({ packName, policy, onClose }: PolicyEditorProps) {
  const [draft, setDraft] = useState<PolicyDraft>(() => draftFromPolicy(policy));
  const [saveError, setSaveError] = useState<string | null>(null);
  const update = useUpdatePolicyMutation();

  const patch = (part: Partial<PolicyDraft>) => setDraft((previous) => ({ ...previous, ...part }));

  const { configuration, error: configurationError } = parseConfiguration(draft.configurationText);
  const deterministicChecks = draft.deterministicChecksText
    .split(",")
    .map((check) => check.trim())
    .filter((check) => check !== "");
  const requiredMissing =
    draft.title.trim() === "" ||
    draft.version.trim() === "" ||
    draft.invariant.trim() === "" ||
    draft.sourceDocument.trim() === "" ||
    draft.sourceSection.trim() === "";
  const saveBlocked = configurationError !== null || requiredMissing;

  const handleSave = (): void => {
    if (saveBlocked || configuration === null) {
      return;
    }
    setSaveError(null);
    const payload: PolicyUpsertRequest = {
      title: draft.title.trim(),
      version: draft.version.trim(),
      status: draft.status,
      severity: draft.severity,
      deterministic_checks: deterministicChecks,
      configuration: configuration as PolicyConfiguration,
      source_document: draft.sourceDocument.trim(),
      source_section: draft.sourceSection.trim(),
      invariant: draft.invariant,
      safe_path: draft.safePath.trim() === "" ? null : draft.safePath.trim(),
      source_version: draft.sourceVersion.trim() === "" ? null : draft.sourceVersion.trim(),
      ownership: policy.ownership,
      scope: policy.scope,
      exceptions: policy.exceptions,
      enforcement: { ...policy.enforcement, deterministic_checks: deterministicChecks },
      tags: parseTags(draft.tagsText),
    };
    update.mutate(
      { packName, policyId: policy.id, payload },
      {
        onSuccess: () => onClose(),
        onError: (error) => setSaveError(describeApiError(error)),
      },
    );
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    handleSave();
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={`Edit policy ${policy.id}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saveBlocked} loading={update.isPending}>
            Save changes
          </Button>
        </>
      }
    >
      <form className="grid gap-3" onSubmit={handleSubmit}>
        {saveError !== null && (
          <Banner variant="error" title="The change was not saved">
            <p>{saveError}</p>
          </Banner>
        )}
        <Input
          label="Title"
          value={draft.title}
          onChange={(event) => patch({ title: event.target.value })}
        />
        <div className="grid gap-3 sm:grid-cols-3">
          <Input
            label="Version"
            value={draft.version}
            onChange={(event) => patch({ version: event.target.value })}
          />
          <Select
            label="Status"
            value={draft.status}
            onChange={(event) => patch({ status: event.target.value })}
          >
            {LIFECYCLE_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </Select>
          <Select
            label="Severity"
            value={draft.severity}
            onChange={(event) => patch({ severity: event.target.value })}
          >
            {SEVERITIES.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </Select>
        </div>
        <Textarea
          label="Invariant"
          rows={2}
          value={draft.invariant}
          onChange={(event) => patch({ invariant: event.target.value })}
        />
        <Input
          label="Tags"
          hint="Comma-separated; order is preserved. Clear the field to remove every tag."
          value={draft.tagsText}
          onChange={(event) => patch({ tagsText: event.target.value })}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <Input
            label="Deterministic checks"
            hint="Comma-separated; leave empty for semantic-only policies."
            value={draft.deterministicChecksText}
            onChange={(event) => patch({ deterministicChecksText: event.target.value })}
          />
          <Input
            label="Safe path"
            value={draft.safePath}
            onChange={(event) => patch({ safePath: event.target.value })}
          />
        </div>
        <Textarea
          label="Configuration"
          rows={6}
          error={configurationError ?? undefined}
          value={draft.configurationText}
          onChange={(event) => patch({ configurationText: event.target.value })}
        />
        <div className="grid gap-3 sm:grid-cols-3">
          <Input
            label="Source document"
            value={draft.sourceDocument}
            onChange={(event) => patch({ sourceDocument: event.target.value })}
          />
          <Input
            label="Source section"
            value={draft.sourceSection}
            onChange={(event) => patch({ sourceSection: event.target.value })}
          />
          <Input
            label="Source version"
            value={draft.sourceVersion}
            onChange={(event) => patch({ sourceVersion: event.target.value })}
          />
        </div>
        <p className="text-xs text-muted">
          Ownership, scope, exceptions, and enforcement metadata are preserved as-is, and the
          platform re-validates provenance on save.
        </p>
      </form>
    </Modal>
  );
}
