import { useState, useMemo } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useSharing, useCreateSharing, useDeleteSharing } from '@/hooks/useSharing';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import type { SharingGrantCreate } from '@/hooks/useSharing';

type ShareMode = 'eenheid' | 'node';

const ACCESS_LABELS: Record<string, string> = {
  read: 'Lezen',
  edit: 'Bewerken',
};

const INITIAL_FORM: SharingGrantCreate & { mode: ShareMode } = {
  mode: 'eenheid',
  source_eenheid_id: undefined,
  source_node_id: undefined,
  target_eenheid_id: '',
  access_level: 'read',
  reason: '',
  geldig_van: '',
  geldig_tot: '',
};

export function SharingManager() {
  const { data: shares, isLoading } = useSharing();
  const { data: eenheden } = useOrganisatieFlat();
  const createSharing = useCreateSharing();
  const deleteSharing = useDeleteSharing();

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const sortedEenheden = useMemo(
    () => [...(eenheden ?? [])].sort((a, b) => a.naam.localeCompare(b.naam)),
    [eenheden],
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const payload: SharingGrantCreate = {
      target_eenheid_id: form.target_eenheid_id,
      access_level: form.access_level,
    };

    if (form.mode === 'eenheid') {
      payload.source_eenheid_id = form.source_eenheid_id;
    } else {
      payload.source_node_id = form.source_node_id;
    }

    if (form.reason?.trim()) payload.reason = form.reason.trim();
    if (form.geldig_van) payload.geldig_van = form.geldig_van;
    if (form.geldig_tot) payload.geldig_tot = form.geldig_tot;

    createSharing.mutate(payload, {
      onSuccess: () => {
        setForm(INITIAL_FORM);
        setShowForm(false);
      },
    });
  };

  const handleDelete = (id: string) => {
    deleteSharing.mutate(id, {
      onSuccess: () => setConfirmDeleteId(null),
    });
  };

  if (isLoading) {
    return <div className="text-sm text-text-secondary py-8 text-center">Laden...</div>;
  }

  return (
    <div className="space-y-4">
      {/* Toggle add form */}
      {!showForm && (
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-primary-600 text-white hover:bg-primary-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Nieuwe deling
        </button>
      )}

      {/* Add form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="border border-border rounded-xl p-4 space-y-3">
          <h3 className="text-sm font-medium text-text">Nieuwe deling aanmaken</h3>

          {/* Mode toggle */}
          <fieldset className="flex gap-4">
            <label className="flex items-center gap-1.5 text-sm text-text cursor-pointer">
              <input
                type="radio"
                name="mode"
                checked={form.mode === 'eenheid'}
                onChange={() =>
                  setForm({ ...form, mode: 'eenheid', source_node_id: undefined })
                }
              />
              Hele eenheid delen
            </label>
            <label className="flex items-center gap-1.5 text-sm text-text cursor-pointer">
              <input
                type="radio"
                name="mode"
                checked={form.mode === 'node'}
                onChange={() =>
                  setForm({ ...form, mode: 'node', source_eenheid_id: undefined })
                }
              />
              Specifiek item delen
            </label>
          </fieldset>

          {/* Source */}
          {form.mode === 'eenheid' ? (
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">
                Broneenheid
              </label>
              <select
                value={form.source_eenheid_id ?? ''}
                onChange={(e) =>
                  setForm({ ...form, source_eenheid_id: e.target.value || undefined })
                }
                className="w-full px-3 py-2 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
                required
              >
                <option value="">Selecteer eenheid...</option>
                {sortedEenheden.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.naam}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">
                Item ID (corpus node)
              </label>
              <input
                type="text"
                value={form.source_node_id ?? ''}
                onChange={(e) =>
                  setForm({ ...form, source_node_id: e.target.value || undefined })
                }
                placeholder="UUID van het item..."
                className="w-full px-3 py-2 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
                required
              />
            </div>
          )}

          {/* Target */}
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">
              Doeleenheid
            </label>
            <select
              value={form.target_eenheid_id}
              onChange={(e) => setForm({ ...form, target_eenheid_id: e.target.value })}
              className="w-full px-3 py-2 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
              required
            >
              <option value="">Selecteer eenheid...</option>
              {sortedEenheden.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.naam}
                </option>
              ))}
            </select>
          </div>

          {/* Access level */}
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">
              Toegangsniveau
            </label>
            <select
              value={form.access_level}
              onChange={(e) =>
                setForm({ ...form, access_level: e.target.value as 'read' | 'edit' })
              }
              className="w-full px-3 py-2 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
            >
              <option value="read">Lezen</option>
              <option value="edit">Bewerken</option>
            </select>
          </div>

          {/* Reason */}
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1">
              Reden (optioneel)
            </label>
            <input
              type="text"
              value={form.reason ?? ''}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
              placeholder="Bijv. samenwerking project X"
              className="w-full px-3 py-2 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
            />
          </div>

          {/* Date range */}
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-text-secondary mb-1">
                Geldig van (optioneel)
              </label>
              <input
                type="date"
                value={form.geldig_van ?? ''}
                onChange={(e) => setForm({ ...form, geldig_van: e.target.value })}
                className="w-full px-3 py-2 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
              />
            </div>
            <div className="flex-1">
              <label className="block text-xs font-medium text-text-secondary mb-1">
                Geldig tot (optioneel)
              </label>
              <input
                type="date"
                value={form.geldig_tot ?? ''}
                onChange={(e) => setForm({ ...form, geldig_tot: e.target.value })}
                className="w-full px-3 py-2 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
              />
            </div>
          </div>

          {/* Form actions */}
          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={createSharing.isPending}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              <Plus className="h-4 w-4" />
              Toevoegen
            </button>
            <button
              type="button"
              onClick={() => {
                setForm(INITIAL_FORM);
                setShowForm(false);
              }}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-gray-200 text-text hover:bg-gray-300 transition-colors"
            >
              Annuleren
            </button>
          </div>
        </form>
      )}

      {/* Shares table */}
      <div className="border border-border rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-border">
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary">Bron</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary">Doel</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden sm:table-cell">
                Niveau
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden md:table-cell">
                Reden
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden lg:table-cell">
                Geldig van
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden lg:table-cell">
                Geldig tot
              </th>
              <th className="w-10 px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {shares?.map((share) => (
              <tr
                key={share.id}
                className="border-b border-border last:border-b-0 hover:bg-gray-50 transition-colors"
              >
                <td className="px-4 py-2.5 text-text">
                  {share.source_eenheid_naam ?? 'Specifiek item'}
                </td>
                <td className="px-4 py-2.5 text-text">
                  {share.target_eenheid_naam ?? share.target_eenheid_id}
                </td>
                <td className="px-4 py-2.5 text-text-secondary hidden sm:table-cell">
                  {ACCESS_LABELS[share.access_level] ?? share.access_level}
                </td>
                <td className="px-4 py-2.5 text-text-secondary hidden md:table-cell">
                  {share.reason || '-'}
                </td>
                <td className="px-4 py-2.5 text-text-secondary hidden lg:table-cell">
                  {new Date(share.geldig_van).toLocaleDateString('nl-NL')}
                </td>
                <td className="px-4 py-2.5 text-text-secondary hidden lg:table-cell">
                  {share.geldig_tot
                    ? new Date(share.geldig_tot).toLocaleDateString('nl-NL')
                    : '-'}
                </td>
                <td className="px-4 py-2.5">
                  {confirmDeleteId === share.id ? (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleDelete(share.id)}
                        disabled={deleteSharing.isPending}
                        className="px-2 py-0.5 text-xs font-medium rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                      >
                        Ja
                      </button>
                      <button
                        onClick={() => setConfirmDeleteId(null)}
                        className="px-2 py-0.5 text-xs font-medium rounded bg-gray-200 text-text hover:bg-gray-300 transition-colors"
                      >
                        Nee
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmDeleteId(share.id)}
                      className="p-1 rounded hover:bg-red-50 text-text-secondary hover:text-red-600 transition-colors"
                      title="Verwijderen"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {(!shares || shares.length === 0) && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-text-secondary">
                  Geen actieve delingen
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-text-secondary">
        Delingen geven een organisatie-eenheid toegang tot gegevens van een andere eenheid of een
        specifiek item. Verwijder een deling om de toegang in te trekken.
      </p>
    </div>
  );
}
