import { useState, type FormEvent } from "react";

import type { Gate, GateRule, GateUpsertRequest, PackValidation } from "../../api";
import {
  describeApiError,
  useDeleteGateMutation,
  useUpsertGateMutation,
  useValidatePackMutation,
} from "../../hooks/usePlatformQueries";
import { Banner, Button, Input, Modal, Select, Table, Td, Th } from "../ui";

const RULE_TYPES = [
  "no-new-findings",
  "max-severity",
  "max-findings",
  "always-block",
  "failure-rate",
] as const;

type RuleType = (typeof RULE_TYPES)[number];

const SEVERITIES = ["info", "low", "medium", "high", "critical"] as const;

function isRuleType(value: string): value is RuleType {
  return (RULE_TYPES as readonly string[]).includes(value);
}

interface RuleDraft {
  type: RuleType;
  severity: string;
  count: string;
  policyIdsText: string;
  maxPercent: string;
}

function makeRuleDraft(): RuleDraft {
  return { type: "no-new-findings", severity: "high", count: "0", policyIdsText: "", maxPercent: "" };
}

function draftFromRule(rule: GateRule): RuleDraft {
  switch (rule.type) {
    case "max-severity":
      return { type: rule.type, severity: rule.severity, count: "0", policyIdsText: "", maxPercent: "" };
    case "max-findings":
      return { type: rule.type, severity: "high", count: String(rule.count), policyIdsText: "", maxPercent: "" };
    case "always-block":
      return {
        type: rule.type,
        severity: "high",
        count: "0",
        policyIdsText: rule.policy_ids.join(", "),
        maxPercent: "",
      };
    case "failure-rate":
      return {
        type: rule.type,
        severity: "high",
        count: "0",
        policyIdsText: "",
        maxPercent: String(rule.max_percent),
      };
    case "no-new-findings":
      return makeRuleDraft();
  }
}

/** Presentational summary of stored rule config; never a computed verdict. */
function describeRule(rule: GateRule): string {
  switch (rule.type) {
    case "no-new-findings":
      return "no new findings";
    case "max-severity":
      return `max severity ${rule.severity}`;
    case "max-findings":
      return `at most ${rule.count} findings`;
    case "always-block":
      return `always block: ${rule.policy_ids.join(", ")}`;
    case "failure-rate":
      return `failure rate under ${rule.max_percent}%`;
  }
}

function serializeRule(draft: RuleDraft): { rule: GateRule | null; error: string | null } {
  switch (draft.type) {
    case "no-new-findings":
      return { rule: { type: "no-new-findings" }, error: null };
    case "max-severity":
      if (draft.severity === "") {
        return { rule: null, error: "Severity is required." };
      }
      return { rule: { type: "max-severity", severity: draft.severity }, error: null };
    case "max-findings": {
      const count = Number(draft.count);
      if (draft.count.trim() === "" || !Number.isInteger(count) || count < 0) {
        return { rule: null, error: "Count must be a non-negative integer." };
      }
      return { rule: { type: "max-findings", count }, error: null };
    }
    case "always-block": {
      const policyIds = draft.policyIdsText
        .split(",")
        .map((id) => id.trim())
        .filter((id) => id !== "");
      if (policyIds.length === 0) {
        return { rule: null, error: "At least one policy ID is required." };
      }
      return { rule: { type: "always-block", policy_ids: policyIds }, error: null };
    }
    case "failure-rate": {
      const maxPercent = Number(draft.maxPercent);
      if (draft.maxPercent.trim() === "" || Number.isNaN(maxPercent)) {
        return { rule: null, error: "Max percent must be a number." };
      }
      return { rule: { type: "failure-rate", max_percent: maxPercent }, error: null };
    }
  }
}

interface GateFormProps {
  packName: string;
  gate: Gate | null;
  onClose: () => void;
}

/**
 * Create/replace form for one gate. Rules are built with typed controls per
 * rule type; an empty rules list is blocked client-side, while everything
 * else (IDs, ranges, pack-level effects) is validated by the server, whose
 * rejections keep this draft open beside the form.
 */
function GateForm({ packName, gate, onClose }: GateFormProps) {
  const [gateId, setGateId] = useState(gate?.id ?? "");
  const [rules, setRules] = useState<RuleDraft[]>(() =>
    gate === null ? [] : gate.rules.map(draftFromRule),
  );
  const [formError, setFormError] = useState<string | null>(null);
  const upsert = useUpsertGateMutation();

  const patchRule = (index: number, part: Partial<RuleDraft>): void => {
    setRules((previous) =>
      previous.map((rule, position) => (position === index ? { ...rule, ...part } : rule)),
    );
  };

  const serialized = rules.map(serializeRule);
  const firstRuleError = serialized.find((entry) => entry.error !== null)?.error ?? null;
  const clientError =
    gateId.trim() === ""
      ? "A gate ID is required."
      : rules.length === 0
        ? "At least one rule is required."
        : firstRuleError;
  const saveBlocked = clientError !== null;

  const handleSave = (): void => {
    if (saveBlocked) {
      return;
    }
    setFormError(null);
    const payloadRules: GateRule[] = [];
    for (const entry of serialized) {
      if (entry.rule !== null) {
        payloadRules.push(entry.rule);
      }
    }
    const payload: GateUpsertRequest = { rules: payloadRules };
    upsert.mutate(
      { packName, gateId: gateId.trim(), payload },
      {
        onSuccess: () => onClose(),
        onError: (error) => setFormError(describeApiError(error)),
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
      title={gate === null ? "New gate" : `Edit gate ${gate.id}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saveBlocked} loading={upsert.isPending}>
            Save gate
          </Button>
        </>
      }
    >
      <form className="grid gap-3" onSubmit={handleSubmit}>
        {clientError !== null && (
          <Banner variant="error" title="The gate cannot be saved yet">
            <p>{clientError}</p>
          </Banner>
        )}
        {formError !== null && (
          <Banner variant="error" title="The platform rejected the gate">
            <p>{formError}</p>
          </Banner>
        )}
        <Input
          label="Gate ID"
          value={gateId}
          disabled={gate !== null}
          hint={gate === null ? "Lowercase letters, digits, dots, and dashes." : undefined}
          onChange={(event) => setGateId(event.target.value)}
        />
        <p className="text-xs text-muted">
          A gate passes only when every rule passes. The platform evaluates gates during scans.
        </p>
        {rules.map((rule, index) => {
          const ruleNumber = index + 1;
          return (
            <div key={ruleNumber} className="grid gap-2 rounded-sm border border-line p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-ink">Rule {ruleNumber}</p>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove rule ${ruleNumber}`}
                  onClick={() => setRules((previous) => previous.filter((_, position) => position !== index))}
                >
                  Remove
                </Button>
              </div>
              <Select
                label={`Rule ${ruleNumber} type`}
                value={rule.type}
                onChange={(event) => {
                  const next = event.target.value;
                  patchRule(index, { type: isRuleType(next) ? next : "no-new-findings" });
                }}
              >
                {RULE_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </Select>
              {rule.type === "max-severity" && (
                <Select
                  label={`Rule ${ruleNumber} severity`}
                  value={rule.severity}
                  onChange={(event) => patchRule(index, { severity: event.target.value })}
                >
                  {SEVERITIES.map((severity) => (
                    <option key={severity} value={severity}>
                      {severity}
                    </option>
                  ))}
                </Select>
              )}
              {rule.type === "max-findings" && (
                <Input
                  label={`Rule ${ruleNumber} count`}
                  type="number"
                  min={0}
                  step={1}
                  value={rule.count}
                  onChange={(event) => patchRule(index, { count: event.target.value })}
                />
              )}
              {rule.type === "always-block" && (
                <Input
                  label={`Rule ${ruleNumber} policy IDs`}
                  hint="Comma-separated policy IDs."
                  value={rule.policyIdsText}
                  onChange={(event) => patchRule(index, { policyIdsText: event.target.value })}
                />
              )}
              {rule.type === "failure-rate" && (
                <Input
                  label={`Rule ${ruleNumber} max percent`}
                  type="number"
                  min={0}
                  max={100}
                  step="any"
                  value={rule.maxPercent}
                  onChange={(event) => patchRule(index, { maxPercent: event.target.value })}
                />
              )}
            </div>
          );
        })}
        <div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setRules((previous) => [...previous, makeRuleDraft()])}
          >
            Add rule
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export interface GateEditorProps {
  packName: string;
  gates: Gate[];
}

/**
 * Gate management for one pack: create, replace, validate the whole pack, and
 * delete. Gates are listed in pack order. Validation and gate results always
 * come from the server — this editor only edits rule configuration.
 */
export function GateEditor({ packName, gates }: GateEditorProps) {
  const [formGate, setFormGate] = useState<Gate | "new" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [validation, setValidation] = useState<PackValidation | null>(null);
  const remove = useDeleteGateMutation();
  const validate = useValidatePackMutation();

  const handleDelete = (gateId: string): void => {
    setActionError(null);
    remove.mutate(
      { packName, gateId },
      { onError: (error) => setActionError(describeApiError(error)) },
    );
  };

  const handleValidate = (): void => {
    setActionError(null);
    setValidation(null);
    validate.mutate(packName, {
      onSuccess: (result) => setValidation(result),
      onError: (error) => setActionError(describeApiError(error)),
    });
  };

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => setFormGate("new")}>
          New gate
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleValidate}
          loading={validate.isPending}
        >
          Validate pack
        </Button>
      </div>
      {actionError !== null && (
        <Banner
          variant="error"
          title="The action did not complete"
          onDismiss={() => setActionError(null)}
        >
          <p>{actionError}</p>
        </Banner>
      )}
      {validation !== null &&
        (validation.valid ? (
          <Banner variant="success" title="Pack is valid.">
            <p>The platform validated the pack file.</p>
          </Banner>
        ) : (
          <Banner variant="error" title="The pack failed validation.">
            <ul className="list-inside list-disc">
              {validation.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </Banner>
        ))}
      <Table
        caption="Quality gates"
        empty={gates.length === 0}
        emptyMessage="No gates are defined for this pack yet."
      >
        <thead>
          <tr>
            <Th>Gate</Th>
            <Th>Rules</Th>
            <Th>Actions</Th>
          </tr>
        </thead>
        <tbody>
          {gates.map((gate) => (
            <tr key={gate.id}>
              <Td className="font-medium">{gate.id}</Td>
              <Td>
                <ul className="grid gap-0.5 text-xs text-muted">
                  {gate.rules.map((rule, index) => (
                    <li key={index}>{describeRule(rule)}</li>
                  ))}
                </ul>
              </Td>
              <Td>
                <div className="flex gap-1.5">
                  <Button
                    variant="secondary"
                    size="sm"
                    aria-label={`Edit gate ${gate.id}`}
                    onClick={() => setFormGate(gate)}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    aria-label={`Delete gate ${gate.id}`}
                    loading={remove.isPending && remove.variables?.gateId === gate.id}
                    onClick={() => handleDelete(gate.id)}
                  >
                    Delete
                  </Button>
                </div>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {formGate !== null && (
        <GateForm
          key={formGate === "new" ? "new" : formGate.id}
          packName={packName}
          gate={formGate === "new" ? null : formGate}
          onClose={() => setFormGate(null)}
        />
      )}
    </div>
  );
}
