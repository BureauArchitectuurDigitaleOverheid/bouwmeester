import { useState } from 'react';
import { Plus, Pencil, Trash2, X } from 'lucide-react';
import {
  useExterneOrganisaties,
  useCreateExterneOrganisatie,
  useUpdateExterneOrganisatie,
  useDeleteExterneOrganisatie,
} from '@/hooks/useExterneOrganisaties';
import {
  EXTERNE_ORG_TYPE_LABELS,
  EXTERNE_ORG_TYPE_COLORS,
  ExterneOrganisatieType,
  type ExterneOrganisatie,
  type ExterneOrganisatieCreate,
} from '@/types';
import { Badge } from '@/components/common/Badge';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';

export function ExterneOrganisatiesPage() {
  const { data: organisaties = [], isLoading } = useExterneOrganisaties();
  const createMutation = useCreateExterneOrganisatie();
  const updateMutation = useUpdateExterneOrganisatie();
  const deleteMutation = useDeleteExterneOrganisatie();

  const [showForm, setShowForm] = useState(false);
  const [editingOrg, setEditingOrg] = useState<ExterneOrganisatie | null>(null);
  const [deleteOrgId, setDeleteOrgId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<ExterneOrganisatieCreate>({
    naam: '',
    type: ExterneOrganisatieType.UITVOERINGSORGANISATIE,
  });

  const resetForm = () => {
    setForm({ naam: '', type: ExterneOrganisatieType.UITVOERINGSORGANISATIE });
    setEditingOrg(null);
    setShowForm(false);
  };

  const startEdit = (org: ExterneOrganisatie) => {
    setEditingOrg(org);
    setForm({
      naam: org.naam,
      afkorting: org.afkorting || undefined,
      type: org.type as ExterneOrganisatieType,
      kvk_nummer: org.kvk_nummer || undefined,
      website: org.website || undefined,
      beschrijving: org.beschrijving || undefined,
    });
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      if (editingOrg) {
        await updateMutation.mutateAsync({ id: editingOrg.id, data: form });
      } else {
        await createMutation.mutateAsync(form);
      }
      resetForm();
    } catch {
      setError(editingOrg ? 'Fout bij opslaan van organisatie.' : 'Fout bij aanmaken van organisatie.');
    }
  };

  const handleDelete = async () => {
    if (!deleteOrgId) return;
    try {
      await deleteMutation.mutateAsync(deleteOrgId);
      setDeleteOrgId(null);
    } catch {
      setError('Fout bij verwijderen van organisatie.');
    }
  };
  const deleteOrgName = organisaties.find((o) => o.id === deleteOrgId)?.naam;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Actions bar */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-secondary">{organisaties.length} organisaties</p>
        <button
          onClick={() => { resetForm(); setShowForm(true); }}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Nieuwe organisatie
        </button>
      </div>

      {/* Inline form */}
      {showForm && (
        <div className="bg-surface rounded-xl border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text">
              {editingOrg ? 'Organisatie bewerken' : 'Nieuwe organisatie'}
            </h3>
            <button onClick={resetForm} className="text-text-secondary hover:text-text transition-colors">
              <X className="h-4 w-4" />
            </button>
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-text mb-1">Naam *</label>
                <input
                  type="text"
                  value={form.naam}
                  onChange={e => setForm(f => ({ ...f, naam: e.target.value }))}
                  required
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-text mb-1">Afkorting</label>
                <input
                  type="text"
                  value={form.afkorting || ''}
                  onChange={e => setForm(f => ({ ...f, afkorting: e.target.value || undefined }))}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-text mb-1">Type *</label>
                <select
                  value={form.type}
                  onChange={e => setForm(f => ({ ...f, type: e.target.value as ExterneOrganisatieType }))}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border"
                >
                  {Object.entries(EXTERNE_ORG_TYPE_LABELS).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-text mb-1">Website</label>
                <input
                  type="url"
                  value={form.website || ''}
                  onChange={e => setForm(f => ({ ...f, website: e.target.value || undefined }))}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border"
                  placeholder="https://..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-text mb-1">KvK-nummer</label>
                <input
                  type="text"
                  value={form.kvk_nummer || ''}
                  onChange={e => setForm(f => ({ ...f, kvk_nummer: e.target.value || undefined }))}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-text mb-1">Beschrijving</label>
              <textarea
                value={form.beschrijving || ''}
                onChange={e => setForm(f => ({ ...f, beschrijving: e.target.value || undefined }))}
                rows={2}
                className="w-full px-3 py-2 text-sm rounded-lg border border-border"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button type="button" onClick={resetForm} className="px-4 py-2 text-sm rounded-lg border border-border hover:bg-gray-50 transition-colors">
                Annuleren
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending || updateMutation.isPending}
                className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
              >
                {editingOrg ? 'Opslaan' : 'Toevoegen'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Error feedback */}
      {error && (
        <div className="p-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-surface rounded-xl border border-border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-gray-50/50">
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Naam</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Afkorting</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Type</th>
              <th className="px-4 py-3 text-left font-medium text-text-secondary">Beschrijving</th>
              <th className="px-4 py-3 w-20"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-text-secondary">Laden...</td></tr>
            ) : organisaties.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-text-secondary">Geen externe organisaties gevonden</td></tr>
            ) : (
              organisaties.map((org) => (
                <tr key={org.id} className="border-b border-border last:border-0 hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-text">{org.naam}</td>
                  <td className="px-4 py-3 text-text-secondary">{org.afkorting || '-'}</td>
                  <td className="px-4 py-3">
                    <Badge variant={EXTERNE_ORG_TYPE_COLORS[org.type as ExterneOrganisatieType] || 'gray'}>
                      {EXTERNE_ORG_TYPE_LABELS[org.type as ExterneOrganisatieType] || org.type}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-text-secondary max-w-[300px] truncate">{org.beschrijving || '-'}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => startEdit(org)}
                        className="p-1.5 rounded-lg text-text-secondary hover:text-text hover:bg-gray-100 transition-colors"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => setDeleteOrgId(org.id)}
                        className="p-1.5 rounded-lg text-text-secondary hover:text-red-600 hover:bg-red-50 transition-colors"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={!!deleteOrgId}
        onClose={() => setDeleteOrgId(null)}
        onConfirm={handleDelete}
        title="Organisatie verwijderen"
        confirmLabel="Verwijderen"
        variant="danger"
        loading={deleteMutation.isPending}
      >
        <p>Weet je zeker dat je <strong>{deleteOrgName}</strong> wilt verwijderen?</p>
      </ConfirmDialog>
    </div>
  );
}
