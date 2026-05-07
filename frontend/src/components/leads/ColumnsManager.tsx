import { useMemo, useState } from 'react';
import {
  Plus,
  Trash2,
  ArrowUp,
  ArrowDown,
  Eye,
  EyeOff,
  Globe,
  Check,
  X,
} from 'lucide-react';
import { Button } from '@/components/common/Button';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
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
      <p className="text-xs text-text-secondary">
        Eigenaren beheren hier de funnel-kolommen voor dit initiatief. Slug
        blijft vast na aanmaken zodat bestaande leads gekoppeld blijven.
        "Actieve fase" telt mee voor de overdue-filter; "Publiek zichtbaar"
        toont casuses op de publieke pagina.
      </p>

      <ul className="divide-y divide-border rounded-xl border border-border">
        {sortedColumns.map((col, idx) => {
          const isFirst = idx === 0;
          const isLast = idx === sortedColumns.length - 1;
          return (
            <li key={col.id} className="px-3 py-2.5 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${col.color}`}
                  >
                    {col.slug}
                  </span>
                  {editing === col.id ? (
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onBlur={commitEdit}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') commitEdit();
                        if (e.key === 'Escape') setEditing(null);
                      }}
                      autoFocus
                      className="flex-1 text-sm rounded-lg border border-border px-2 py-1 focus:outline-none focus:ring-2 focus:ring-primary"
                    />
                  ) : (
                    <button
                      type="button"
                      onClick={() => startEdit(col)}
                      className="text-sm font-medium text-text hover:text-primary-700 truncate text-left"
                      title="Klik om te hernoemen"
                    >
                      {col.name}
                    </button>
                  )}
                  <span className="text-xs text-text-secondary tabular-nums">
                    {col.lead_count} {col.lead_count === 1 ? 'lead' : 'leads'}
                  </span>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() => moveColumn(col, 'up')}
                    disabled={isFirst || reorderMutation.isPending}
                    className="p-1 rounded hover:bg-gray-100 text-text-secondary disabled:opacity-30"
                    title="Omhoog"
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => moveColumn(col, 'down')}
                    disabled={isLast || reorderMutation.isPending}
                    className="p-1 rounded hover:bg-gray-100 text-text-secondary disabled:opacity-30"
                    title="Omlaag"
                  >
                    <ArrowDown className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeletingId(col.id)}
                    disabled={sortedColumns.length <= 1}
                    className="p-1 rounded hover:bg-gray-100 text-text-secondary hover:text-red-500 disabled:opacity-30 disabled:hover:text-text-secondary"
                    title={
                      sortedColumns.length <= 1
                        ? 'Laatste kolom kan niet weg'
                        : 'Verwijderen'
                    }
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-3 flex-wrap pl-1 text-xs">
                <button
                  type="button"
                  onClick={() => toggleActive(col)}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${
                    col.is_active_stage
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-gray-100 text-gray-600'
                  }`}
                  title="Telt mee voor overdue/stale-filter"
                >
                  {col.is_active_stage ? (
                    <Check className="h-3 w-3" />
                  ) : (
                    <X className="h-3 w-3" />
                  )}
                  Actieve fase
                </button>
                <button
                  type="button"
                  onClick={() => togglePublic(col)}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${
                    col.is_public_visible
                      ? 'bg-blue-100 text-blue-800'
                      : 'bg-gray-100 text-gray-600'
                  }`}
                  title="Toont casuses op publieke pagina"
                >
                  {col.is_public_visible ? (
                    <Eye className="h-3 w-3" />
                  ) : (
                    <EyeOff className="h-3 w-3" />
                  )}
                  Publiek zichtbaar
                </button>
                <div className="flex items-center gap-1">
                  <Globe className="h-3 w-3 text-text-secondary" />
                  <ColorSwatches
                    selected={col.color}
                    onSelect={(color) => setColor(col, color)}
                  />
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      {adding ? (
        <div className="rounded-xl border border-border p-3 space-y-2">
          <input
            type="text"
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
            placeholder="Kolomnaam (bv. Strategisch)"
            className="w-full text-sm rounded-lg border border-border px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary"
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
        <Button
          variant="secondary"
          size="sm"
          icon={<Plus className="h-3.5 w-3.5" />}
          onClick={() => setAdding(true)}
        >
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
                <select
                  value={moveTarget}
                  onChange={(e) => setMoveTarget(e.target.value)}
                  className="w-full text-sm rounded-lg border border-border px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="">— Kies kolom —</option>
                  {otherColumns.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
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
