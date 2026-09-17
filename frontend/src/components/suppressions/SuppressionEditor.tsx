import { useState, type FormEvent } from "react";

import type { Suppression, SuppressionInput, SuppressionUpdateInput } from "../../api";
import {
  describeApiError,
  useCreateSuppressionMutation,
  useUpdateSuppressionMutation,
} from "../../hooks/usePlatformQueries";
import { Banner, Button, Input, Modal, Textarea } from "../ui";

const EXPIRY_HINT =
  "An expired suppression does not waive a current finding; the platform enforces expiry at scan time. Timestamps are UTC.";

/** ISO-8601 wire value rendered into a datetime-local control (UTC wall time). */
function isoToLocalInput(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return parsed.toISOString().slice(0, 16);
}

/** datetime-local control value converted back to the ISO-8601 wire format. */
function localInputToIso(value: string): string | null {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toISOString();
}

export interface SuppressionEditorProps {
  /** null creates a new suppression; otherwise the editable audit fields open prefilled. */
  suppression: Suppression | null;
  onClose: () => void;
}

/**
 * Create/edit form for operational suppressions, reusing the existing
 * create/update client routes. Required fields block saving until complete;
 * server rejections keep the draft open with a safe error.
 */
export function SuppressionEditor({ suppression, onClose }: SuppressionEditorProps) {
  const isEdit = suppression !== null;
  const [policyId, setPolicyId] = useState(suppression?.policy_id ?? "");
  const [fingerprint, setFingerprint] = useState(suppression?.fingerprint ?? "");
  const [reason, setReason] = useState(suppression?.reason ?? "");
  const [owner, setOwner] = useState(suppression?.owner ?? "");
  const [expiresAt, setExpiresAt] = useState(() =>
    suppression === null ? "" : isoToLocalInput(suppression.expires_at),
  );
  const [saveError, setSaveError] = useState<string | null>(null);
  const create = useCreateSuppressionMutation();
  const update = useUpdateSuppressionMutation();

  const expiryIso = expiresAt === "" ? null : localInputToIso(expiresAt);
  const requiredMissing =
    policyId.trim() === "" ||
    fingerprint.trim() === "" ||
    reason.trim() === "" ||
    owner.trim() === "" ||
    expiryIso === null;

  const handleSave = (): void => {
    if (requiredMissing || expiryIso === null) {
      return;
    }
    setSaveError(null);
    if (suppression === null) {
      const payload: SuppressionInput = {
        policy_id: policyId.trim(),
        fingerprint: fingerprint.trim(),
        reason: reason.trim(),
        owner: owner.trim(),
        expires_at: expiryIso,
      };
      create.mutate(payload, {
        onSuccess: () => onClose(),
        onError: (error) => setSaveError(describeApiError(error)),
      });
    } else {
      const payload: SuppressionUpdateInput = {
        reason: reason.trim(),
        owner: owner.trim(),
        expires_at: expiryIso,
      };
      update.mutate(
        { id: suppression.id, payload },
        {
          onSuccess: () => onClose(),
          onError: (error) => setSaveError(describeApiError(error)),
        },
      );
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    handleSave();
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? `Edit suppression ${suppression?.id ?? ""}` : "New suppression"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={requiredMissing}
            loading={create.isPending || update.isPending}
          >
            Save suppression
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
        {!isEdit && (
          <>
            <Input
              label="Policy ID"
              value={policyId}
              onChange={(event) => setPolicyId(event.target.value)}
            />
            <Input
              label="Fingerprint"
              hint="Fingerprint of the finding being waived."
              value={fingerprint}
              onChange={(event) => setFingerprint(event.target.value)}
            />
          </>
        )}
        <Textarea
          label="Reason"
          rows={2}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <Input label="Owner" value={owner} onChange={(event) => setOwner(event.target.value)} />
        <Input
          label="Expires at"
          type="datetime-local"
          hint={EXPIRY_HINT}
          value={expiresAt}
          onChange={(event) => setExpiresAt(event.target.value)}
        />
      </form>
    </Modal>
  );
}
