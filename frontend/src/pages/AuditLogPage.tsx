import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useActivityFeed } from '@/hooks/useActivity';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import {
  Activity,
  EVENT_TYPE_LABELS,
  EVENT_TYPE_CATEGORY_LABELS,
  NODE_TYPE_LABELS,
  STAKEHOLDER_ROL_LABELS,
  TASK_PRIORITY_LABELS,
  TASK_STATUS_LABELS,
} from '@/types';

const PAGE_SIZE = 25;

const CATEGORY_OPTIONS = [
  { value: '', label: 'Alle categorieën' },
  ...Object.entries(EVENT_TYPE_CATEGORY_LABELS).map(([value, label]) => ({
    value,
    label,
  })),
];

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('nl-NL', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Translate known values to Dutch display labels. */
function humanizeValue(key: string, value: unknown): string {
  const str = String(value);

  if (key === 'node_type') {
    return NODE_TYPE_LABELS[str as keyof typeof NODE_TYPE_LABELS] || str;
  }

  if (
    key === 'rol' ||
    key === 'old_rol' ||
    key === 'new_rol'
  ) {
    return STAKEHOLDER_ROL_LABELS[str] || str;
  }

  if (key === 'priority') {
    return TASK_PRIORITY_LABELS?.[str] || str;
  }

  if (key === 'old_status' || key === 'new_status') {
    return TASK_STATUS_LABELS?.[str] || str;
  }

  return str;
}

/** Keys we never show in the details column. */
const HIDDEN_KEYS = new Set([
  'actor_naam',
  // UUIDs that we show as named entities instead
  'person_id',
  'tag_id',
  'from_node_id',
  'to_node_id',
  'assignee_id',
  'old_assignee_id',
  'new_assignee_id',
  'eigenaar_id',
  'organisatie_eenheid_id',
  'organisatie_id',
  'node_id',
  'task_id',
  'edge_id',
  'suggested_edge_id',
  'item_id',
  'placement_id',
]);

/** Presentable detail chips: label → display value. */
function buildChips(
  item: Activity,
): Array<{ label: string; value: string; highlight?: boolean }> {
  const d = item.details || {};
  const chips: Array<{ label: string; value: string; highlight?: boolean }> = [];

  // Node type
  if (d.node_type) {
    chips.push({
      label: 'Type',
      value: humanizeValue('node_type', d.node_type),
    });
  }

  // Person name (stakeholder events)
  if (d.person_naam) {
    chips.push({ label: 'Persoon', value: String(d.person_naam) });
  }

  // Roles
  if (d.rol) {
    chips.push({
      label: 'Rol',
      value: humanizeValue('rol', d.rol),
    });
  }
  if (d.old_rol && d.new_rol) {
    chips.push({
      label: 'Rol',
      value: `${humanizeValue('old_rol', d.old_rol)} → ${humanizeValue('new_rol', d.new_rol)}`,
    });
  }

  // Tag name
  if (d.tag_name) {
    chips.push({ label: 'Tag', value: String(d.tag_name) });
  }

  // Edge node titles
  if (d.from_node_title && d.to_node_title) {
    chips.push({
      label: 'Relatie',
      value: `${d.from_node_title} → ${d.to_node_title}`,
    });
  }
  if (d.edge_type) {
    chips.push({ label: 'Type', value: String(d.edge_type) });
  }

  // Task-specific
  if (d.priority) {
    chips.push({
      label: 'Prioriteit',
      value: humanizeValue('priority', d.priority),
    });
  }
  if (d.assignee_naam) {
    chips.push({ label: 'Toegewezen aan', value: String(d.assignee_naam) });
  }
  if (d.new_assignee_naam) {
    chips.push({
      label: 'Nieuw toegewezen',
      value: String(d.new_assignee_naam),
    });
  }

  // Status change
  if (d.old_status && d.new_status) {
    chips.push({
      label: 'Status',
      value: `${humanizeValue('old_status', d.old_status)} → ${humanizeValue('new_status', d.new_status)}`,
      highlight: true,
    });
  }

  // Org placement
  if (d.organisatie_eenheid_naam) {
    chips.push({
      label: 'Eenheid',
      value: String(d.organisatie_eenheid_naam),
    });
  }
  if (d.dienstverband) {
    chips.push({
      label: 'Dienstverband',
      value: String(d.dienstverband),
    });
  }

  // Import count
  if (d.count != null) {
    chips.push({ label: 'Aantal', value: String(d.count) });
  }

  return chips;
}

/** Render the details column. */
function DetailCell({
  item,
  onOpenNode,
  onOpenTask,
}: {
  item: Activity;
  onOpenNode: (id: string) => void;
  onOpenTask: (id: string) => void;
}) {
  const d = item.details || {};
  const subject = d.title || d.naam || d.name;
  const chips = buildChips(item);

  // Determine what clicking the subject should do
  const handleClick = () => {
    if (item.task_id && item.event_type.startsWith('task.')) {
      onOpenTask(item.task_id);
    } else if (item.node_id) {
      onOpenNode(item.node_id);
    }
  };

  const isClickable =
    (item.task_id && item.event_type.startsWith('task.')) || item.node_id;

  return (
    <div className="space-y-1">
      {subject && (
        <div className="font-medium text-text">
          {isClickable ? (
            <button
              onClick={handleClick}
              className="text-left hover:text-primary-600 hover:underline cursor-pointer"
            >
              {String(subject)}
            </button>
          ) : (
            String(subject)
          )}
        </div>
      )}
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chips.map((chip, i) => (
            <span
              key={i}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${
                chip.highlight
                  ? 'bg-blue-50 text-blue-700'
                  : 'bg-gray-100 text-text-secondary'
              }`}
            >
              <span className="font-medium">{chip.label}:</span> {chip.value}
            </span>
          ))}
        </div>
      )}
      {!subject && chips.length === 0 && (
        <span className="text-text-tertiary">—</span>
      )}
    </div>
  );
}

export function AuditLogPage() {
  const [page, setPage] = useState(0);
  const [category, setCategory] = useState('');
  const { openNodeDetail } = useNodeDetail();
  const { openTaskDetail } = useTaskDetail();

  const { data, isLoading, isError } = useActivityFeed({
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
    event_type: category || undefined,
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <div className="p-6 space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3">
        <select
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(0);
          }}
          className="px-3 py-2 rounded-lg border border-border text-sm bg-white focus:outline-none focus:border-primary-400"
        >
          {CATEGORY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="border border-border rounded-xl overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-border">
              <th className="text-left px-4 py-3 font-medium text-text-secondary w-40">
                Tijdstip
              </th>
              <th className="text-left px-4 py-3 font-medium text-text-secondary w-56">
                Actie
              </th>
              <th className="text-left px-4 py-3 font-medium text-text-secondary w-40">
                Actor
              </th>
              <th className="text-left px-4 py-3 font-medium text-text-secondary">
                Details
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td
                  colSpan={4}
                  className="px-4 py-8 text-center text-text-secondary"
                >
                  Laden...
                </td>
              </tr>
            ) : isError ? (
              <tr>
                <td
                  colSpan={4}
                  className="px-4 py-8 text-center text-red-600"
                >
                  Fout bij laden van activiteiten
                </td>
              </tr>
            ) : !data?.items.length ? (
              <tr>
                <td
                  colSpan={4}
                  className="px-4 py-8 text-center text-text-secondary"
                >
                  Geen activiteit gevonden
                </td>
              </tr>
            ) : (
              data.items.map((item) => (
                <tr
                  key={item.id}
                  className="border-b border-border last:border-b-0 hover:bg-gray-50"
                >
                  <td className="px-4 py-3 text-text-secondary whitespace-nowrap align-top">
                    {formatDate(item.created_at)}
                  </td>
                  <td className="px-4 py-3 text-text align-top">
                    {EVENT_TYPE_LABELS[item.event_type] || item.event_type}
                  </td>
                  <td className="px-4 py-3 text-text align-top">
                    {item.actor_naam || (
                      <span className="text-text-tertiary">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <DetailCell
                      item={item}
                      onOpenNode={openNodeDetail}
                      onOpenTask={openTaskDetail}
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-text-secondary">
            {data?.total ?? 0} resultaten — pagina {page + 1} van {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border text-sm disabled:opacity-40 hover:bg-gray-50 transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
              Vorige
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border text-sm disabled:opacity-40 hover:bg-gray-50 transition-colors"
            >
              Volgende
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
