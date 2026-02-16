import { useState } from 'react';
import { Plus, Filter, X } from 'lucide-react';
import { useOpdrachten } from '@/hooks/useOpdrachten';
import { useExterneOrganisaties } from '@/hooks/useExterneOrganisaties';
import { OpdrachtForm } from '@/components/opdrachten/OpdrachtForm';
import { OpdrachtDetail } from '@/components/opdrachten/OpdrachtDetail';
import {
  OPDRACHT_TYPE_LABELS,
  OPDRACHT_STATUS_LABELS,
  OPDRACHT_STATUS_COLORS,
  OPDRACHT_TYPE_COLORS,
  type OpdrachtFilters,
  OpdrachtType,
  OpdrachtStatus,
} from '@/types';
import { Badge } from '@/components/common/Badge';
import { formatCurrency } from '@/utils/format';

export function OpdrachtenPage() {
  const [filters, setFilters] = useState<OpdrachtFilters>({});
  const [showForm, setShowForm] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  const { data: opdrachten = [], isLoading } = useOpdrachten(filters);
  const { data: externeOrgs = [] } = useExterneOrganisaties();

  const years = [...new Set(opdrachten.map(o => o.begrotingsjaar))].sort((a, b) => b - a);
  const allYears = years.length > 0 ? years : [2024, 2025, 2026];

  const totaalBudget = opdrachten.reduce((sum, o) => sum + (o.budget || 0), 0);
  const totaalGerealiseerd = opdrachten.reduce((sum, o) => sum + (o.gerealiseerd || 0), 0);
  const uitnutting = totaalBudget > 0 ? (totaalGerealiseerd / totaalBudget * 100) : 0;

  if (selectedId) {
    return (
      <OpdrachtDetail
        opdrachtId={selectedId}
        onBack={() => setSelectedId(null)}
      />
    );
  }

  if (showForm) {
    return (
      <OpdrachtForm
        onClose={() => setShowForm(false)}
        onSuccess={() => setShowForm(false)}
      />
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="bg-surface rounded-xl border border-border p-4">
          <p className="text-sm text-text-secondary">Aantal opdrachten</p>
          <p className="text-2xl font-semibold text-text">{opdrachten.length}</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-4">
          <p className="text-sm text-text-secondary">Totaal budget</p>
          <p className="text-2xl font-semibold text-text">{formatCurrency(totaalBudget)}</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-4">
          <p className="text-sm text-text-secondary">Totaal gerealiseerd</p>
          <p className="text-2xl font-semibold text-text">{formatCurrency(totaalGerealiseerd)}</p>
        </div>
        <div className="bg-surface rounded-xl border border-border p-4">
          <p className="text-sm text-text-secondary">Uitnutting</p>
          <p className="text-2xl font-semibold text-text">{uitnutting.toFixed(1)}%</p>
        </div>
      </div>

      {/* Actions bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-border hover:bg-gray-50 transition-colors"
          >
            <Filter className="h-4 w-4" />
            Filters
          </button>
          {Object.keys(filters).length > 0 && (
            <button
              onClick={() => setFilters({})}
              className="flex items-center gap-1 px-2 py-1 text-xs text-text-secondary hover:text-text transition-colors"
            >
              <X className="h-3 w-3" />
              Wis filters
            </button>
          )}
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Nieuwe opdracht
        </button>
      </div>

      {/* Filters panel */}
      {showFilters && (
        <div className="bg-surface rounded-xl border border-border p-4 grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">Begrotingsjaar</label>
            <select
              value={filters.begrotingsjaar ?? ''}
              onChange={(e) => setFilters(f => ({ ...f, begrotingsjaar: e.target.value ? Number(e.target.value) : undefined }))}
              className="w-full px-3 py-1.5 text-sm rounded-lg border border-border"
            >
              <option value="">Alle jaren</option>
              {allYears.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">Type</label>
            <select
              value={filters.type ?? ''}
              onChange={(e) => setFilters(f => ({ ...f, type: e.target.value || undefined }))}
              className="w-full px-3 py-1.5 text-sm rounded-lg border border-border"
            >
              <option value="">Alle typen</option>
              {Object.entries(OPDRACHT_TYPE_LABELS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">Status</label>
            <select
              value={filters.status ?? ''}
              onChange={(e) => setFilters(f => ({ ...f, status: e.target.value || undefined }))}
              className="w-full px-3 py-1.5 text-sm rounded-lg border border-border"
            >
              <option value="">Alle statussen</option>
              {Object.entries(OPDRACHT_STATUS_LABELS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">Opdrachtnemer</label>
            <select
              value={filters.opdrachtnemer_id ?? ''}
              onChange={(e) => setFilters(f => ({ ...f, opdrachtnemer_id: e.target.value || undefined }))}
              className="w-full px-3 py-1.5 text-sm rounded-lg border border-border"
            >
              <option value="">Alle opdrachtnemers</option>
              {externeOrgs.map(o => (
                <option key={o.id} value={o.id}>{o.afkorting || o.naam}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-surface rounded-xl border border-border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-gray-50/50">
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Titel</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Type</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Jaar</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Opdrachtnemer</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Instrument</th>
              <th className="px-4 py-3 text-right font-medium text-text-secondary">Budget</th>
              <th className="px-4 py-3 text-right font-medium text-text-secondary">Gerealiseerd</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-text-secondary">Laden...</td></tr>
            ) : opdrachten.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-text-secondary">Geen opdrachten gevonden</td></tr>
            ) : (
              opdrachten.map((o) => (
                <tr
                  key={o.id}
                  onClick={() => setSelectedId(o.id)}
                  className="border-b border-border last:border-0 hover:bg-gray-50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-medium text-text max-w-[300px] truncate">{o.titel}</td>
                  <td className="px-4 py-3">
                    <Badge variant={OPDRACHT_TYPE_COLORS[o.type as OpdrachtType] || 'gray'}>
                      {OPDRACHT_TYPE_LABELS[o.type as OpdrachtType] || o.type}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-text-secondary">{o.begrotingsjaar}</td>
                  <td className="px-4 py-3 text-text-secondary">{o.opdrachtnemer?.afkorting || o.opdrachtnemer?.naam || '-'}</td>
                  <td className="px-4 py-3 text-text-secondary truncate max-w-[200px]">{o.instrument?.title || '-'}</td>
                  <td className="px-4 py-3 text-right text-text tabular-nums">{formatCurrency(o.budget)}</td>
                  <td className="px-4 py-3 text-right text-text tabular-nums">{formatCurrency(o.gerealiseerd)}</td>
                  <td className="px-4 py-3">
                    <Badge variant={OPDRACHT_STATUS_COLORS[o.status as OpdrachtStatus] || 'gray'}>
                      {OPDRACHT_STATUS_LABELS[o.status as OpdrachtStatus] || o.status}
                    </Badge>
                  </td>
                </tr>
              ))
            )}
          </tbody>
          {opdrachten.length > 0 && (
            <tfoot>
              <tr className="border-t-2 border-border bg-gray-50/50 font-medium">
                <td colSpan={5} className="px-4 py-3 text-text">Totaal ({opdrachten.length} opdrachten)</td>
                <td className="px-4 py-3 text-right text-text tabular-nums">{formatCurrency(totaalBudget)}</td>
                <td className="px-4 py-3 text-right text-text tabular-nums">{formatCurrency(totaalGerealiseerd)}</td>
                <td className="px-4 py-3"></td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}
