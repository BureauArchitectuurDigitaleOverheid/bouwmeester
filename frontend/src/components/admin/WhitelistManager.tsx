import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useWhitelist, useAddWhitelistEmail, useRemoveWhitelistEmail } from '@/hooks/useAdmin';

export function WhitelistManager() {
  const { data: emails, isLoading } = useWhitelist();
  const addEmail = useAddWhitelistEmail();
  const removeEmail = useRemoveWhitelistEmail();
  const [newEmail, setNewEmail] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newEmail.trim();
    if (!trimmed) return;
    addEmail.mutate(trimmed, {
      onSuccess: () => setNewEmail(''),
    });
  };

  const handleDelete = (id: string) => {
    removeEmail.mutate(id, {
      onSuccess: () => setConfirmDeleteId(null),
    });
  };

  if (isLoading) {
    return <div className="text-sm text-text-secondary py-8 text-center">Laden...</div>;
  }

  return (
    <div className="space-y-4">
      {/* Add form */}
      <form onSubmit={handleAdd} className="flex gap-2">
        <input
          type="email"
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
          placeholder="E-mailadres toevoegen..."
          className="flex-1 px-3 py-2 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
          required
        />
        <button
          type="submit"
          disabled={addEmail.isPending || !newEmail.trim()}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Toevoegen
        </button>
      </form>

      {/* Email list */}
      <div className="border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-border">
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary">E-mailadres</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden sm:table-cell">Toegevoegd door</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden sm:table-cell">Datum</th>
              <th className="w-10 px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {emails?.map((entry) => (
              <tr key={entry.id} className="border-b border-border last:border-b-0 hover:bg-gray-50 transition-colors">
                <td className="px-4 py-2.5 text-text">{entry.email}</td>
                <td className="px-4 py-2.5 text-text-secondary hidden sm:table-cell">
                  {entry.added_by || '-'}
                </td>
                <td className="px-4 py-2.5 text-text-secondary hidden sm:table-cell">
                  {new Date(entry.created_at).toLocaleDateString('nl-NL')}
                </td>
                <td className="px-4 py-2.5">
                  {confirmDeleteId === entry.id ? (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleDelete(entry.id)}
                        disabled={removeEmail.isPending}
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
                      onClick={() => setConfirmDeleteId(entry.id)}
                      className="p-1 rounded hover:bg-red-50 text-text-secondary hover:text-red-600 transition-colors"
                      title="Verwijderen"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {(!emails || emails.length === 0) && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-text-secondary">
                  Geen e-mailadressen op de toegangslijst
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-text-secondary">
        Alleen personen met een e-mailadres op deze lijst kunnen inloggen.
        Wanneer de lijst leeg is, is alle toegang open (lokale ontwikkeling).
      </p>
    </div>
  );
}
