import { useState, useMemo } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight, Clock, Building2, User } from 'lucide-react';
import { Badge } from '@/components/common/Badge';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { useUpdateTask } from '@/hooks/useTasks';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { usePeople } from '@/hooks/usePeople';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import {
  TASK_PRIORITY_LABELS,
  TASK_PRIORITY_COLORS,
  ORGANISATIE_TYPE_LABELS,
} from '@/types';
import type { Task } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';

const PERSON_LEVEL_TYPES = new Set(['afdeling', 'team']);

function getDescendantIds(allUnits: { id: string; parent_id?: string | null }[], parentId: string): Set<string> {
  const descendants = new Set<string>();
  const queue = [parentId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const u of allUnits) {
      if (u.parent_id === current && !descendants.has(u.id)) {
        descendants.add(u.id);
        queue.push(u.id);
      }
    }
  }
  return descendants;
}

interface UnassignedTasksSectionProps {
  noUnitTasks: Task[];
  noUnitCount: number;
  noPersonTasks: Task[];
  noPersonCount: number;
  showNoUnit: boolean;
  eenheidType: string;
  selectedEenheidId: string;
}

function TaskRow({ task, showPersonAssign, selectedEenheidId }: { task: Task; showPersonAssign: boolean; selectedEenheidId: string }) {
  const { openTaskDetail } = useTaskDetail();
  const updateTask = useUpdateTask();
  const { data: eenheden } = useOrganisatieFlat();
  const { data: allPeople } = usePeople();

  const isOverdue = task.due_date && new Date(task.due_date) < new Date();

  const eenheidOptions: SelectOption[] = useMemo(() => {
    const all = eenheden ?? [];
    const descendantIds = selectedEenheidId ? getDescendantIds(all, selectedEenheidId) : new Set<string>();
    const filtered = selectedEenheidId
      ? all.filter((e) => descendantIds.has(e.id))
      : all;
    return [
      { value: '', label: 'Geen' },
      ...filtered.map((e) => ({
        value: e.id,
        label: e.naam,
        description: ORGANISATIE_TYPE_LABELS[e.type] ?? e.type,
      })),
    ];
  }, [eenheden, selectedEenheidId]);

  const personOptions: SelectOption[] = useMemo(() => {
    if (!showPersonAssign) return [];
    const people = allPeople ?? [];
    const eenheidId = task.organisatie_eenheid_id;
    if (eenheidId) {
      const filtered = people.filter((p) => p.organisatie_eenheid_id === eenheidId);
      if (filtered.length > 0) {
        return filtered.map((p) => ({
          value: p.id,
          label: p.naam,
          description: p.functie ?? undefined,
        }));
      }
    }
    return people.map((p) => ({
      value: p.id,
      label: p.naam,
      description: p.functie ?? undefined,
    }));
  }, [allPeople, task.organisatie_eenheid_id, showPersonAssign]);

  const handleUnitChange = (value: string) => {
    updateTask.mutate({
      id: task.id,
      data: { organisatie_eenheid_id: value || undefined },
    });
  };

  const handlePersonChange = (value: string) => {
    updateTask.mutate({
      id: task.id,
      data: { assignee_id: value || undefined },
    });
  };

  return (
    <div className="flex items-center gap-3 py-2.5 px-4 border-b border-border last:border-0 hover:bg-gray-50/50">
      <div className="flex-1 min-w-0">
        <button
          onClick={() => openTaskDetail(task.id)}
          className="text-sm font-medium text-text hover:text-primary-700 text-left truncate block max-w-full"
        >
          {task.title}
        </button>
        <div className="flex items-center gap-2 mt-1">
          <Badge
            variant={TASK_PRIORITY_COLORS[task.priority] as 'blue'}
            dot
          >
            {TASK_PRIORITY_LABELS[task.priority]}
          </Badge>
          {task.due_date && (
            <span
              className={`inline-flex items-center gap-1 text-xs ${
                isOverdue ? 'text-red-600 font-medium' : 'text-text-secondary'
              }`}
            >
              <Clock className="h-3 w-3" />
              {new Date(task.due_date).toLocaleDateString('nl-NL', {
                day: 'numeric',
                month: 'short',
              })}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <div className="w-56">
          <CreatableSelect
            value={task.organisatie_eenheid_id ?? ''}
            onChange={handleUnitChange}
            options={eenheidOptions}
            placeholder="Eenheid..."
          />
        </div>
        {showPersonAssign && (
          <div className="w-56">
            <CreatableSelect
              value={task.assignee_id ?? ''}
              onChange={handlePersonChange}
              options={personOptions}
              placeholder="Persoon..."
            />
          </div>
        )}
      </div>
    </div>
  );
}

export function UnassignedTasksSection({
  noUnitTasks,
  noUnitCount,
  noPersonTasks,
  noPersonCount,
  showNoUnit,
  eenheidType,
  selectedEenheidId,
}: UnassignedTasksSectionProps) {
  const [noUnitOpen, setNoUnitOpen] = useState(true);
  const [noPersonOpen, setNoPersonOpen] = useState(true);

  const isPersonLevel = PERSON_LEVEL_TYPES.has(eenheidType);
  const showNoPersonSection = isPersonLevel;
  const totalCount = (showNoUnit ? noUnitCount : 0) + (showNoPersonSection ? noPersonCount : 0);
  if (totalCount === 0) return null;

  return (
    <div className="bg-surface rounded-xl border border-border shadow-sm">
      <div className="flex items-center gap-3 px-5 py-4">
        <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-amber-100 text-amber-600">
          <AlertTriangle className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-text">Onverdeeld</h2>
          <p className="text-sm text-text-secondary">
            {totalCount} {totalCount === 1 ? 'taak' : 'taken'} zonder toewijzing
          </p>
        </div>
      </div>

      {/* No unit section */}
      {showNoUnit && noUnitCount > 0 && (
        <div className="border-t border-border">
          <button
            onClick={() => setNoUnitOpen(!noUnitOpen)}
            className="flex items-center gap-2 w-full px-5 py-3 text-sm font-medium text-text-secondary hover:bg-gray-50"
          >
            {noUnitOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            <Building2 className="h-4 w-4" />
            Geen eenheid
            <span className="ml-1 text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full">
              {noUnitCount}
            </span>
          </button>
          {noUnitOpen && (
            <div>
              {noUnitTasks.map((task) => (
                <TaskRow key={task.id} task={task} showPersonAssign={false} selectedEenheidId={selectedEenheidId} />
              ))}
              {noUnitCount > noUnitTasks.length && (
                <p className="px-5 py-2 text-xs text-text-secondary">
                  En nog {noUnitCount - noUnitTasks.length} meer...
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* No person section — only at afdeling/team level */}
      {showNoPersonSection && noPersonCount > 0 && (
        <div className="border-t border-border">
          <button
            onClick={() => setNoPersonOpen(!noPersonOpen)}
            className="flex items-center gap-2 w-full px-5 py-3 text-sm font-medium text-text-secondary hover:bg-gray-50"
          >
            {noPersonOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            <User className="h-4 w-4" />
            Geen persoon
            <span className="ml-1 text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full">
              {noPersonCount}
            </span>
          </button>
          {noPersonOpen && (
            <div>
              {noPersonTasks.map((task) => (
                <TaskRow key={task.id} task={task} showPersonAssign={isPersonLevel} selectedEenheidId={selectedEenheidId} />
              ))}
              {noPersonCount > noPersonTasks.length && (
                <p className="px-5 py-2 text-xs text-text-secondary">
                  En nog {noPersonCount - noPersonTasks.length} meer...
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
