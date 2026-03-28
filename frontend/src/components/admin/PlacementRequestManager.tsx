import { useState } from 'react';
import { Check, X } from 'lucide-react';
import { usePendingPlacements, useApprovePlacement, useDenyPlacement } from '@/hooks/useOrgPlacements';
import { DIENSTVERBAND_LABELS } from '@/types';

export function PlacementRequestManager() {
  const { data: requests, isLoading } = usePendingPlacements();
  const approveRequest = useApprovePlacement();
  const denyRequest = useDenyPlacement();
  const [confirmDenyId, setConfirmDenyId] = useState<string | null>(null);

  const handleApprove = (id: string) => {
    approveRequest.mutate(id);
  };

  const handleDeny = (id: string) => {
    denyRequest.mutate(id, {
      onSuccess: () => setConfirmDenyId(null),
    });
  };

  if (isLoading) {
    return <div className="text-sm text-text-secondary py-8 text-center">Laden...</div>;
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-text-secondary">
        Nieuwe medewerkers die zich aanmelden kiezen een team. Hieronder kun je hun plaatsingsverzoek goedkeuren of afwijzen.
      </p>

      <div className="border border-border rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-border">
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary">Naam</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary">Team</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden sm:table-cell">Dienstverband</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden sm:table-cell">Datum</th>
              <th className="w-24 px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {requests?.map((req) => (
              <tr key={req.id} className="border-b border-border last:border-b-0 hover:bg-gray-50 transition-colors">
                <td className="px-4 py-2.5 text-text font-medium">{req.person_naam}</td>
                <td className="px-4 py-2.5 text-text">{req.eenheid_naam}</td>
                <td className="px-4 py-2.5 text-text-secondary hidden sm:table-cell">
                  {DIENSTVERBAND_LABELS[req.dienstverband] || req.dienstverband}
                </td>
                <td className="px-4 py-2.5 text-text-secondary hidden sm:table-cell">
                  {new Date(req.requested_at).toLocaleDateString('nl-NL', {
                    day: 'numeric',
                    month: 'short',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </td>
                <td className="px-4 py-2.5">
                  {confirmDenyId === req.id ? (
                    <div className="flex gap-1">
                      <button
                        onClick={() => handleDeny(req.id)}
                        disabled={denyRequest.isPending}
                        className="px-2 py-0.5 text-xs font-medium rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                      >
                        Bevestig
                      </button>
                      <button
                        onClick={() => setConfirmDenyId(null)}
                        className="px-2 py-0.5 text-xs font-medium rounded bg-gray-200 text-text hover:bg-gray-300 transition-colors"
                      >
                        Annuleren
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleApprove(req.id)}
                        disabled={approveRequest.isPending}
                        className="p-1 rounded hover:bg-green-50 text-text-secondary hover:text-green-600 transition-colors"
                        title="Goedkeuren"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setConfirmDenyId(req.id)}
                        className="p-1 rounded hover:bg-red-50 text-text-secondary hover:text-red-600 transition-colors"
                        title="Afwijzen"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {(!requests || requests.length === 0) && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-text-secondary">
                  Geen openstaande plaatsingsverzoeken
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
