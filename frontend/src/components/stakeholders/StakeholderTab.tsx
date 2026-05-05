import { useMemo, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { Badge } from '@/components/common/Badge';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import {
  useStakeholderAssessments,
  useCreateStakeholderAssessment,
  useUpdateStakeholderAssessment,
  useDeleteStakeholderAssessment,
} from '@/hooks/useStakeholderAssessments';
import { usePeople } from '@/hooks/usePeople';
import {
  STAKEHOLDER_HOUDING_LABELS,
  STAKEHOLDER_HOUDING_COLORS,
} from '@/types';
import type {
  StakeholderAssessment,
  StakeholderHouding,
  StakeholderScopeType,
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
        <ul className="divide-y divide-border rounded-xl border border-border">
          {assessments.map((a) => (
            <li key={a.id} className="px-3 py-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium text-sm text-text">
                  {a.person_naam}
                </div>
                {!readOnly && (
                  <button
                    onClick={() => handleDelete(a)}
                    className="p-1 rounded hover:bg-gray-100 text-text-secondary hover:text-red-500 transition-colors"
                    title="Verwijderen"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
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
                <textarea
                  value={a.notitie ?? ''}
                  onChange={(e) =>
                    handleUpdate(a, { notitie: e.target.value || null })
                  }
                  placeholder="Notitie (optioneel)"
                  rows={2}
                  className="w-full text-sm rounded-lg border border-border px-2 py-1 focus:outline-none focus:ring-2 focus:ring-primary"
                />
              )}
              {readOnly && a.notitie && (
                <p className="text-sm text-text-secondary whitespace-pre-wrap">
                  {a.notitie}
                </p>
              )}
            </li>
          ))}
        </ul>
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
    <label className="flex flex-col gap-0.5">
      <span className="text-xs text-text-secondary">{label}</span>
      <select
        value={value ?? ''}
        onChange={(e) =>
          onChange(e.target.value === '' ? null : Number(e.target.value))
        }
        disabled={disabled}
        className="text-sm rounded-lg border border-border px-2 py-1 focus:outline-none focus:ring-2 focus:ring-primary disabled:bg-gray-50"
      >
        <option value="">—</option>
        {SCORE_OPTIONS.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
    </label>
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
          <Badge className={STAKEHOLDER_HOUDING_COLORS[value]}>
            {STAKEHOLDER_HOUDING_LABELS[value]}
          </Badge>
        ) : (
          <span className="text-sm text-text-secondary">—</span>
        )}
      </div>
    );
  }
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-xs text-text-secondary">Houding</span>
      <select
        value={value ?? ''}
        onChange={(e) =>
          onChange(
            e.target.value === ''
              ? null
              : (e.target.value as StakeholderHouding),
          )
        }
        className="text-sm rounded-lg border border-border px-2 py-1 focus:outline-none focus:ring-2 focus:ring-primary"
      >
        <option value="">—</option>
        {HOUDING_OPTIONS.map((h) => (
          <option key={h} value={h}>
            {STAKEHOLDER_HOUDING_LABELS[h]}
          </option>
        ))}
      </select>
    </label>
  );
}
