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

  if (isLoading) return <LoadingSpinner className="py-6" />;

  return (
    <div className="space-y-3">
      {assessments.length === 0 ? (
        <p className="text-sm text-text-secondary">
          Nog geen stakeholders geregistreerd.
        </p>
      ) : (
        <nldd-list type="form" variant="box-tinted" accessible-label="Stakeholders">
          {assessments.map((a) => (
            <nldd-list-item key={a.id}>
              <div className="w-full py-1 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium text-sm text-text">
                    {a.person_naam}
                  </div>
                  {!readOnly && (
                    <NlddIconButton
                      icon="trash"
                      accessibleLabel="Stakeholder verwijderen"
                      variant="neutral-transparent"
                      size="sm"
                      onClick={() => handleDelete(a)}
                    />
                  )}
                </div>
                <div className="grid grid-cols-3 gap-2">
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
                </div>
                {!readOnly && (
                  <NoteEditor
                    value={a.notitie}
                    onPersist={(value) => handleUpdate(a, { notitie: value })}
                  />
                )}
                {readOnly && a.notitie && (
                  <RichTextDisplay content={a.notitie} fallback="" />
                )}
              </div>
            </nldd-list-item>
          ))}
        </nldd-list>
      )}

      {!readOnly && (
        <div className="flex items-start gap-2">
          <div className="flex-1">
            <CreatableSelect
              value={addValue}
              onChange={(v) => {
                setAddValue(v);
                if (v) handleAdd(v);
              }}
              options={availableOptions}
              placeholder="Persoon toevoegen..."
            />
          </div>
        </div>
      )}
    </div>
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
  return (
    <nldd-form-field label={label}>
      <nldd-dropdown size="sm" {...(disabled ? { disabled: true } : {})}>
        <select
          aria-label={label}
          value={value ?? ''}
          onChange={(e) =>
            onChange(e.target.value === '' ? null : Number(e.target.value))
          }
          disabled={disabled}
        >
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
  if (disabled) {
    return (
      <div className="flex flex-col gap-0.5">
        <span className="text-xs text-text-secondary">Houding</span>
        {value ? (
          <Badge variant={HOUDING_BADGE_VARIANT[value]}>
            {STAKEHOLDER_HOUDING_LABELS[value]}
          </Badge>
        ) : (
          <span className="text-sm text-text-secondary">—</span>
        )}
      </div>
    );
  }
  return (
    <nldd-form-field label="Houding">
      <nldd-dropdown size="sm">
        <select
          aria-label="Houding"
          value={value ?? ''}
          onChange={(e) =>
            onChange(
              e.target.value === ''
                ? null
                : (e.target.value as StakeholderHouding),
            )
          }
        >
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
