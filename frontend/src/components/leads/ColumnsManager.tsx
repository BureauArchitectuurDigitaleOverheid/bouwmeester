import { useCallback, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/common/Button';
import { Select } from '@/components/common/Select';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { eventValue, useNlddEvent } from '@/components/nldd/events';
import {
  useCreateLeadColumn,
  useDeleteLeadColumn,
  useLeadColumns,
  useReorderLeadColumns,
  useUpdateLeadColumn,
} from '@/hooks/useLeadColumns';
import type { LeadColumn } from '@/types';

const COLOR_PRESETS: { label: string; value: string }[] = [
  { label: 'Indigo', value: 'bg-indigo-100 text-indigo-800' },
  { label: 'Blauw', value: 'bg-blue-100 text-blue-800' },
  { label: 'Geel', value: 'bg-yellow-100 text-yellow-800' },
  { label: 'Oranje', value: 'bg-orange-100 text-orange-800' },
  { label: 'Paars', value: 'bg-purple-100 text-purple-800' },
  { label: 'Groen', value: 'bg-green-100 text-green-800' },
  { label: 'Grijs', value: 'bg-gray-100 text-gray-800' },
  { label: 'Roze', value: 'bg-pink-100 text-pink-800' },
  { label: 'Rood', value: 'bg-red-100 text-red-800' },
  { label: 'Smaragd', value: 'bg-emerald-100 text-emerald-800' },
];

interface ColumnsManagerProps {
  initiatiefId: string;
}

export function ColumnsManager({ initiatiefId }: ColumnsManagerProps) {
  const { columns, isLoading } = useLeadColumns(initiatiefId);
  const createMutation = useCreateLeadColumn(initiatiefId);
  const updateMutation = useUpdateLeadColumn(initiatiefId);
  const deleteMutation = useDeleteLeadColumn(initiatiefId);
  const reorderMutation = useReorderLeadColumns(initiatiefId);

  const [adding, setAdding] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [draftColor, setDraftColor] = useState(COLOR_PRESETS[0].value);
  const [editing, setEditing] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [moveTarget, setMoveTarget] = useState<string>('');

  const sortedColumns = useMemo(
    () => [...columns].sort((a, b) => a.sort_order - b.sort_order),
    [columns],
  );

  const deletingColumn = sortedColumns.find((c) => c.id === deletingId) ?? null;
  const otherColumns = sortedColumns.filter((c) => c.id !== deletingId);

  const handleAdd = async () => {
    const name = draftName.trim();
    if (!name) return;
    await createMutation.mutateAsync({ name, color: draftColor });
    setDraftName('');
    setDraftColor(COLOR_PRESETS[0].value);
    setAdding(false);
  };

  const startEdit = (col: LeadColumn) => {
    setEditing(col.id);
    setEditName(col.name);
  };

  const commitEdit = async () => {
    if (!editing) return;
    const name = editName.trim();
    if (!name) {
      setEditing(null);
      return;
    }
    await updateMutation.mutateAsync({ id: editing, data: { name } });
    setEditing(null);
  };

  const moveColumn = async (col: LeadColumn, dir: 'up' | 'down') => {
    const idx = sortedColumns.findIndex((c) => c.id === col.id);
    const targetIdx = dir === 'up' ? idx - 1 : idx + 1;
    if (targetIdx < 0 || targetIdx >= sortedColumns.length) return;
    const next = [...sortedColumns];
    [next[idx], next[targetIdx]] = [next[targetIdx], next[idx]];
    await reorderMutation.mutateAsync(next.map((c) => c.id));
  };

  const setColor = async (col: LeadColumn, color: string) => {
    await updateMutation.mutateAsync({ id: col.id, data: { color } });
  };

  const toggleActive = async (col: LeadColumn) => {
    await updateMutation.mutateAsync({
      id: col.id,
      data: { is_active_stage: !col.is_active_stage },
    });
  };

  const togglePublic = async (col: LeadColumn) => {
    await updateMutation.mutateAsync({
      id: col.id,
      data: { is_public_visible: !col.is_public_visible },
    });
  };

  const confirmDelete = async () => {
    if (!deletingColumn) return;
    const needsMove = deletingColumn.lead_count > 0;
    if (needsMove && !moveTarget) return;
    await deleteMutation.mutateAsync({
      id: deletingColumn.id,
      moveTo: needsMove ? moveTarget : undefined,
    });
    setDeletingId(null);
    setMoveTarget('');
  };

  if (isLoading) {
    return <LoadingSpinner className="py-6" />;
  }

  return (
    <div className="space-y-3">
      <nldd-text size="xs" color="secondary">
        Eigenaren beheren hier de funnel-kolommen voor dit initiatief. Slug
        blijft vast na aanmaken zodat bestaande leads gekoppeld blijven.
        "Actieve fase" telt mee voor de overdue-filter; "Publiek zichtbaar"
        toont casuses op de publieke pagina.
      </nldd-text>

      <nldd-list variant="box-tinted" dividers="always" accessible-label="Funnel-kolommen">
        {sortedColumns.map((col, idx) => (
          <ColumnRow
            key={col.id}
            col={col}
            isFirst={idx === 0}
            isLast={idx === sortedColumns.length - 1}
            reordering={reorderMutation.isPending}
            canDelete={sortedColumns.length > 1}
            editing={editing === col.id}
            editName={editName}
            onEditNameChange={setEditName}
            onStartEdit={() => startEdit(col)}
            onCommitEdit={commitEdit}
            onCancelEdit={() => setEditing(null)}
            onMoveUp={() => moveColumn(col, 'up')}
            onMoveDown={() => moveColumn(col, 'down')}
            onDelete={() => setDeletingId(col.id)}
            onToggleActive={() => toggleActive(col)}
            onTogglePublic={() => togglePublic(col)}
            onSetColor={(color) => setColor(col, color)}
          />
        ))}
      </nldd-list>

      {adding ? (
        <div className="rounded-xl border border-border p-3 space-y-2">
          <nldd-text-field
            value={draftName}
            onChange={(e) => setDraftName((e.target as HTMLInputElement).value)}
            placeholder="Kolomnaam (bv. Strategisch)"
            accessible-label="Kolomnaam"
            autoFocus
          />
          <div className="flex items-center justify-between gap-2">
            <ColorSwatches selected={draftColor} onSelect={setDraftColor} />
            <div className="flex gap-1">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setAdding(false);
                  setDraftName('');
                }}
              >
                Annuleren
              </Button>
              <Button
                size="sm"
                onClick={handleAdd}
                loading={createMutation.isPending}
                disabled={!draftName.trim()}
              >
                Toevoegen
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <Button variant="secondary" size="sm" icon="plus" onClick={() => setAdding(true)}>
          Kolom toevoegen
        </Button>
      )}

      <ConfirmDialog
        open={!!deletingColumn}
        onClose={() => {
          setDeletingId(null);
          setMoveTarget('');
        }}
        onConfirm={confirmDelete}
        title="Kolom verwijderen"
        confirmLabel="Verwijderen"
        variant="danger"
        loading={deleteMutation.isPending}
      >
        {deletingColumn && (
          <div className="space-y-3">
            <p>
              Weet je zeker dat je <strong>{deletingColumn.name}</strong> wilt
              verwijderen?
            </p>
            {deletingColumn.lead_count > 0 ? (
              <div className="space-y-1">
                <p className="text-sm text-text-secondary">
                  Deze kolom bevat {deletingColumn.lead_count}{' '}
                  {deletingColumn.lead_count === 1 ? 'lead' : 'leads'}. Kies een
                  doel-kolom waar ze heen gaan:
                </p>
                <Select
                  value={moveTarget}
                  onChange={(e) => setMoveTarget(e.target.value)}
                  placeholder="— Kies kolom —"
                  options={otherColumns.map((c) => ({ value: c.id, label: c.name }))}
                />
              </div>
            ) : (
              <p className="text-sm text-text-secondary">
                De kolom is leeg en wordt direct verwijderd.
              </p>
            )}
          </div>
        )}
      </ConfirmDialog>
    </div>
  );
}

interface ColumnRowProps {
  col: LeadColumn;
  isFirst: boolean;
  isLast: boolean;
  reordering: boolean;
  canDelete: boolean;
  editing: boolean;
  editName: string;
  onEditNameChange: (value: string) => void;
  onStartEdit: () => void;
  onCommitEdit: () => void;
  onCancelEdit: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onDelete: () => void;
  onToggleActive: () => void;
  onTogglePublic: () => void;
  onSetColor: (color: string) => void;
}

/**
 * One column row: a segmented `nldd-list-item` (rename control, reorder and
 * delete icon buttons) plus a second line of toggle chips. The chips stay
 * plain buttons rather than nldd-tag: they are two-state toggles the user
 * clicks to flip, not status labels, and nldd-tag has no click semantics.
 */
function ColumnRow({
  col,
  isFirst,
  isLast,
  reordering,
  canDelete,
  editing,
  editName,
  onEditNameChange,
  onStartEdit,
  onCommitEdit,
  onCancelEdit,
  onMoveUp,
  onMoveDown,
  onDelete,
  onToggleActive,
  onTogglePublic,
  onSetColor,
}: ColumnRowProps) {
  const nameFieldRef = useRef<HTMLElement>(null);
  const renameTriggerRef = useRef<HTMLElement>(null);

  useNlddEvent(nameFieldRef, 'input', (e) => onEditNameChange(eventValue(e)));
  useNlddEvent(
    nameFieldRef,
    'blur',
    useCallback(() => onCommitEdit(), [onCommitEdit]),
  );
  useNlddEvent(renameTriggerRef, 'click', onStartEdit);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') onCommitEdit();
    if (e.key === 'Escape') onCancelEdit();
  };

  return (
    <nldd-list-item>
      <div className="flex flex-col gap-2 py-1 w-full">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${col.color}`}>
              {col.slug}
            </span>
            {editing ? (
              <nldd-text-field
                ref={nameFieldRef}
                value={editName}
                onKeyDown={handleKeyDown}
                autoFocus
                accessible-label="Kolomnaam"
                style={{ flex: 1 }}
              />
            ) : (
              <nldd-list-item-segment ref={renameTriggerRef} button accessible-label={`${col.name} hernoemen`}>
                {col.name}
              </nldd-list-item-segment>
            )}
            <nldd-text size="xs" color="secondary" className="tabular-nums">
              {col.lead_count} {col.lead_count === 1 ? 'lead' : 'leads'}
            </nldd-text>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            <NlddIconButton
              icon="chevron-up"
              accessibleLabel="Omhoog"
              variant="neutral-transparent"
              size="sm"
              disabled={isFirst || reordering}
              onClick={onMoveUp}
            />
            <NlddIconButton
              icon="chevron-down"
              accessibleLabel="Omlaag"
              variant="neutral-transparent"
              size="sm"
              disabled={isLast || reordering}
              onClick={onMoveDown}
            />
            <NlddIconButton
              icon="trash"
              accessibleLabel={canDelete ? 'Verwijderen' : 'Laatste kolom kan niet weg'}
              variant="neutral-transparent"
              size="sm"
              disabled={!canDelete}
              onClick={onDelete}
            />
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap pl-1 text-xs">
          <ToggleChip
            active={col.is_active_stage}
            activeIcon="check-mark"
            inactiveIcon="close"
            label="Actieve fase"
            title="Telt mee voor overdue/stale-filter"
            activeClassName="bg-emerald-100 text-emerald-800"
            onToggle={onToggleActive}
          />
          <ToggleChip
            active={col.is_public_visible}
            activeIcon="eye"
            inactiveIcon="eye-slash"
            label="Publiek zichtbaar"
            title="Toont casuses op publieke pagina"
            activeClassName="bg-blue-100 text-blue-800"
            onToggle={onTogglePublic}
          />
          <div className="flex items-center gap-1">
            <nldd-icon name="globe" size="16" color="secondary-content" aria-hidden="true" />
            <ColorSwatches selected={col.color} onSelect={onSetColor} />
          </div>
        </div>
      </div>
    </nldd-list-item>
  );
}

interface ToggleChipProps {
  active: boolean;
  activeIcon: string;
  inactiveIcon: string;
  label: string;
  title: string;
  activeClassName: string;
  onToggle: () => void;
}

function ToggleChip({ active, activeIcon, inactiveIcon, label, title, activeClassName, onToggle }: ToggleChipProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onToggle);

  return (
    <nldd-list-item-segment
      ref={ref}
      button
      title={title}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${active ? activeClassName : 'bg-gray-100 text-gray-600'}`}
    >
      <nldd-icon name={active ? activeIcon : inactiveIcon} size="16" aria-hidden="true" />
      {label}
    </nldd-list-item-segment>
  );
}

function ColorSwatches({
  selected,
  onSelect,
}: {
  selected: string;
  onSelect: (color: string) => void;
}) {
  return (
    <div className="flex gap-1">
      {COLOR_PRESETS.map((preset) => (
        <button
          key={preset.value}
          type="button"
          onClick={() => onSelect(preset.value)}
          title={preset.label}
          className={`h-4 w-4 rounded-full border ${
            preset.value
          } ${selected === preset.value ? 'ring-2 ring-offset-1 ring-current' : ''}`}
        >
          <span className="sr-only">{preset.label}</span>
        </button>
      ))}
    </div>
  );
}
