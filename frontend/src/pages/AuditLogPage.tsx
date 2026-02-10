import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useActivityFeed } from '@/hooks/useActivity';
import { EVENT_TYPE_LABELS, EVENT_TYPE_CATEGORY_LABELS } from '@/types';

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

function formatDetails(details?: Record<string, unknown>): string {
  if (!details) return '';
  return Object.entries(details)
    .filter(([, v]) => v != null)
    .map(([k, v]) => `${k}: ${v}`)
    .join(', ');
}

export function AuditLogPage() {
  const [page, setPage] = useState(0);
  const [category, setCategory] = useState('');

  const { data, isLoading } = useActivityFeed({
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
              <th className="text-left px-4 py-3 font-medium text-text-secondary">
                Tijdstip
              </th>
              <th className="text-left px-4 py-3 font-medium text-text-secondary">
                Actie
              </th>
              <th className="text-left px-4 py-3 font-medium text-text-secondary">
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
                  <td className="px-4 py-3 text-text-secondary whitespace-nowrap">
                    {formatDate(item.created_at)}
                  </td>
                  <td className="px-4 py-3 text-text">
                    {EVENT_TYPE_LABELS[item.event_type] || item.event_type}
                  </td>
                  <td className="px-4 py-3 text-text">
                    {item.actor_naam || '\u2014'}
                  </td>
                  <td className="px-4 py-3 text-text-secondary max-w-md truncate">
                    {formatDetails(item.details)}
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
