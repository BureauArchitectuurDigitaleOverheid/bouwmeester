import { useEffect, useMemo, useRef, useState } from 'react';
import { Badge } from '@/components/common/Badge';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { eventValue, useNlddEvent, useNlddValue } from '@/components/nldd/events';
import {
  useStakeholderAssessments,
  useCreateStakeholderAssessment,
  useUpdateStakeholderAssessment,
  useDeleteStakeholderAssessment,
} from '@/hooks/useStakeholderAssessments';
import { usePeople } from '@/hooks/usePeople';
import { STAKEHOLDER_HOUDING_LABELS } from '@/types';
import type {
  StakeholderAssessment,
  StakeholderHouding,
  StakeholderScopeType,
  BadgeVariant,
} from '@/types';

interface StakeholderTabProps {
  scopeType: StakeholderScopeType;
  scopeId: string;
  readOnly?: boolean;
}

const HOUDING_OPTIONS: StakeholderHouding[] = [
  'tegen',
  'kritisch',
  'neutraal',
  'welwillend',
  'voorstander',
];

const SCORE_OPTIONS = [1, 2, 3, 4, 5];

/**
 * Houding -> Badge variant, replacing the pre-existing STAKEHOLDER_HOUDING_COLORS
 * (raw Tailwind bg-/text- classes from `@/types`). That constant painted nothing
 * once Badge moved to nldd-tag: the wrapper only takes a semantic/Rijkshuisstijl
 * `variant`, and forwarding arbitrary Tailwind classes as `className` no longer
 * has anything to attach to. Pre-existing bug, not introduced by this
 * conversion — flagged rather than fixed at the source, since `@/types` is
 * outside this pass's scope.
 */
const HOUDING_BADGE_VARIANT: Record<StakeholderHouding, BadgeVariant> = {
  tegen: 'red',
  kritisch: 'orange',
  neutraal: 'slate',
  welwillend: 'emerald',
  voorstander: 'green',
};

export function StakeholderTab({
  scopeType,
  scopeId,
  readOnly = false,
}: StakeholderTabProps) {
  const { data: assessments = [], isLoading } = useStakeholderAssessments(
    scopeType,
    scopeId,
  );
  const { data: allPeople = [] } = usePeople();
  const createMutation = useCreateStakeholderAssessment();
  const updateMutation = useUpdateStakeholderAssessment();
  const deleteMutation = useDeleteStakeholderAssessment();
  const [addValue, setAddValue] = useState('');

  const availableOptions = useMemo(() => {
    const linkedIds = new Set(assessments.map((a) => a.person_id));
    return allPeople
      .filter((p) => !linkedIds.has(p.id) && !p.is_agent)
      .map((p) => ({ value: p.id, label: p.naam }));
  }, [allPeople, assessments]);

  const handleAdd = async (personId: string) => {
    if (!personId) return;
    await createMutation.mutateAsync({
      person_id: personId,
      scope_type: scopeType,
      scope_id: scopeId,
    });
    setAddValue('');
  };

  const handleUpdate = (
    a: StakeholderAssessment,
    patch: Partial<StakeholderAssessment>,
  ) => {
    updateMutation.mutate({
      id: a.id,
      data: patch,
      scopeType,
      scopeId,
    });
  };

  const handleDelete = (a: StakeholderAssessment) => {
    deleteMutation.mutate({ id: a.id, scopeType, scopeId });
  };

  if (isLoading) {
    return (
      <nldd-container padding-block="24">
        <LoadingSpinner />
      </nldd-container>
    );
  }

  return (
    <nldd-container gap="12">
      {assessments.length === 0 ? (
        <nldd-text size="sm" color="secondary">
          Nog geen stakeholders geregistreerd.
        </nldd-text>
      ) : (
        <nldd-list type="form" variant="box-tinted" accessible-label="Stakeholders">
          {assessments.map((a) => (
            <nldd-list-item key={a.id}>
              {/* A row this complex (name, delete action, three selects, a
                  note editor) is more than text-cell can carry, so it goes in
                  a single full-width nldd-cell per the "multiple paragraphs
                  or markup in a row" guidance from the list-with-rows pattern. */}
              <nldd-cell width="full">
                <nldd-container gap="8" padding-block="4">
                  <nldd-container layout="row" gap="8" vertical-alignment="center">
                    <nldd-text weight="medium" size="sm">{a.person_naam}</nldd-text>
                    <nldd-spacer size="flexible" />
                    {!readOnly && (
                      <NlddIconButton
                        icon="trash"
                        accessibleLabel="Stakeholder verwijderen"
                        variant="neutral-transparent"
                        size="sm"
                        onClick={() => handleDelete(a)}
                      />
                    )}
                  </nldd-container>
                  <nldd-container layout="grid" column-count={3} gap="8">
                    <ScoreSelect
                      label="Belang"
                      value={a.belang}
                      onChange={(v) => handleUpdate(a, { belang: v })}
                      disabled={readOnly}
                    />
                    <HoudingSelect
                      value={a.houding}
                      onChange={(v) => handleUpdate(a, { houding: v })}
                      disabled={readOnly}
                    />
                    <ScoreSelect
                      label="Invloed"
                      value={a.invloed}
                      onChange={(v) => handleUpdate(a, { invloed: v })}
                      disabled={readOnly}
                    />
                  </nldd-container>
                  {!readOnly && (
                    <NoteEditor
                      value={a.notitie}
                      onPersist={(value) => handleUpdate(a, { notitie: value })}
                    />
                  )}
                  {readOnly && a.notitie && (
                    <RichTextDisplay content={a.notitie} fallback="" />
                  )}
                </nldd-container>
              </nldd-cell>
            </nldd-list-item>
          ))}
        </nldd-list>
      )}

      {!readOnly && (
        <nldd-container width="full">
          <CreatableSelect
            value={addValue}
            onChange={(v) => {
              setAddValue(v);
              if (v) handleAdd(v);
            }}
            options={availableOptions}
            placeholder="Persoon toevoegen..."
          />
        </nldd-container>
      )}
    </nldd-container>
  );
}

function ScoreSelect({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  disabled?: boolean;
}) {
  // nldd-dropdown stops the slotted select's native `change` and re-emits its
  // own CustomEvent from the host, so a React onChange on the select never
  // fires (see src/components/nldd/events.ts). Listen on the dropdown instead.
  // This component is instantiated once per row in a `.map()`, so its own
  // useRef is already scoped per row — no extra extraction needed.
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (e) => {
    const next = eventValue(e);
    onChange(next === '' ? null : Number(next));
  });

  return (
    <nldd-form-field label={label}>
      <nldd-dropdown ref={ref} size="sm" {...(disabled ? { disabled: true } : {})}>
        <select aria-label={label} value={value ?? ''} onChange={() => {}} disabled={disabled}>
          <option value="">—</option>
          {SCORE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </nldd-dropdown>
    </nldd-form-field>
  );
}

function HoudingSelect({
  value,
  onChange,
  disabled,
}: {
  value: StakeholderHouding | null;
  onChange: (v: StakeholderHouding | null) => void;
  disabled?: boolean;
}) {
  // Same nldd-dropdown wiring as ScoreSelect above. Declared before the
  // `disabled` early return below so the hook always runs (Rules of Hooks);
  // it's simply unused in the disabled branch.
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (e) => {
    const next = eventValue(e);
    onChange(next === '' ? null : (next as StakeholderHouding));
  });

  if (disabled) {
    return (
      <nldd-container gap="2">
        <nldd-text size="xs" color="secondary">Houding</nldd-text>
        {value ? (
          <Badge variant={HOUDING_BADGE_VARIANT[value]}>
            {STAKEHOLDER_HOUDING_LABELS[value]}
          </Badge>
        ) : (
          <nldd-text size="sm" color="secondary">—</nldd-text>
        )}
      </nldd-container>
    );
  }

  return (
    <nldd-form-field label="Houding">
      <nldd-dropdown ref={ref} size="sm">
        <select aria-label="Houding" value={value ?? ''} onChange={() => {}}>
          <option value="">—</option>
          {HOUDING_OPTIONS.map((h) => (
            <option key={h} value={h}>
              {STAKEHOLDER_HOUDING_LABELS[h]}
            </option>
          ))}
        </select>
      </nldd-dropdown>
    </nldd-form-field>
  );
}

function NoteEditor({
  value,
  onPersist,
}: {
  value: string | null;
  onPersist: (v: string | null) => void;
}) {
  // Local draft so typing doesn't fire a PUT per keystroke. Persist on blur.
  // Sync from server only when not actively editing.
  const [draft, setDraft] = useState(value ?? '');
  const [focused, setFocused] = useState(false);
  const ref = useRef<HTMLElement & { value?: string }>(null);

  useEffect(() => {
    if (!focused) {
      setDraft(value ?? '');
    }
  }, [value, focused]);

  useNlddValue(ref, draft);
  useNlddEvent(ref, 'input', (e) => setDraft(eventValue(e)));
  useNlddEvent(ref, 'focus', () => setFocused(true));
  useNlddEvent(ref, 'blur', () => {
    setFocused(false);
    const next = draft.trim() ? draft : null;
    if (next !== (value ?? null)) {
      onPersist(next);
    }
  });

  return (
    <nldd-multi-line-text-field
      ref={ref}
      placeholder="Notitie (optioneel)"
      rows={2}
      accessible-label="Notitie"
    />
  );
}
