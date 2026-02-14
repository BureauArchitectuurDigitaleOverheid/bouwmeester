import { useState } from 'react';
import { Check, X } from 'lucide-react';
import { useAccessRequests, useReviewAccessRequest } from '@/hooks/useAdmin';

export function AccessRequestManager() {
  const [filter, setFilter] = useState<string>('pending');
  const { data: requests, isLoading } = useAccessRequests(filter || undefined);
  const reviewRequest = useReviewAccessRequest();
  const [denyId, setDenyId] = useState<string | null>(null);
  const [denyReason, setDenyReason] = useState('');

  const handleApprove = (id: string) => {
    reviewRequest.mutate({ id, action: 'approve' });
  };

  const handleDeny = (id: string) => {
    reviewRequest.mutate(
      { id, action: 'deny', deny_reason: denyReason || undefined },
      { onSuccess: () => { setDenyId(null); setDenyReason(''); } }
    );
  };

  if (isLoading) {
    return <div className="text-sm text-text-secondary py-8 text-center">Laden...</div>;
  }

  return (
    <div className="space-y-4">
      {/* Filter */}
      <div className="flex gap-2">
        {[
          { value: 'pending', label: 'In afwachting' },
          { value: '', label: 'Alle' },
        ].map((opt) => (
          <button
            key={opt.value}
            onClick={() => setFilter(opt.value)}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              filter === opt.value
                ? 'bg-primary-100 text-primary-700 font-medium'
                : 'text-text-secondary hover:bg-gray-100'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Request list */}
      <div className="border border-border rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-border">
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary">Naam</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary">E-mailadres</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden sm:table-cell">Datum</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden sm:table-cell">Status</th>
              <th className="w-24 px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {requests?.map((req) => (
              <tr key={req.id} className="border-b border-border last:border-b-0 hover:bg-gray-50 transition-colors">
                <td className="px-4 py-2.5 text-text font-medium">{req.naam}</td>
                <td className="px-4 py-2.5 text-text break-all">{req.email}</td>
                <td className="px-4 py-2.5 text-text-secondary hidden sm:table-cell">
                  {new Date(req.requested_at).toLocaleDateString('nl-NL', {
                    day: 'numeric',
                    month: 'short',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </td>
                <td className="px-4 py-2.5 hidden sm:table-cell">
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      req.status === 'pending'
                        ? 'bg-amber-100 text-amber-700'
                        : req.status === 'approved'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-red-100 text-red-700'
                    }`}
                  >
                    {req.status === 'pending' ? 'In afwachting' : req.status === 'approved' ? 'Goedgekeurd' : 'Afgewezen'}
                  </span>
                </td>
                <td className="px-4 py-2.5">
                  {req.status === 'pending' && (
                    <>
                      {denyId === req.id ? (
                        <div className="flex flex-col gap-1">
                          <input
                            type="text"
                            value={denyReason}
                            onChange={(e) => setDenyReason(e.target.value)}
                            placeholder="Reden (optioneel)"
                            className="px-2 py-1 text-xs rounded border border-border focus:outline-none focus:border-primary-400"
                            autoFocus
                          />
                          <div className="flex gap-1">
                            <button
                              onClick={() => handleDeny(req.id)}
                              disabled={reviewRequest.isPending}
                              className="px-2 py-0.5 text-xs font-medium rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                            >
                              Afwijzen
                            </button>
                            <button
                              onClick={() => { setDenyId(null); setDenyReason(''); }}
                              className="px-2 py-0.5 text-xs font-medium rounded bg-gray-200 text-text hover:bg-gray-300 transition-colors"
                            >
                              Annuleren
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleApprove(req.id)}
                            disabled={reviewRequest.isPending}
                            className="p-1 rounded hover:bg-green-50 text-text-secondary hover:text-green-600 transition-colors"
                            title="Goedkeuren"
                          >
                            <Check className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => { setDenyId(req.id); setDenyReason(''); }}
                            className="p-1 rounded hover:bg-red-50 text-text-secondary hover:text-red-600 transition-colors"
                            title="Afwijzen"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      )}
                    </>
                  )}
                  {req.status === 'denied' && req.deny_reason && (
                    <span className="text-xs text-text-secondary" title={req.deny_reason}>
                      {req.deny_reason.length > 20 ? `${req.deny_reason.slice(0, 20)}...` : req.deny_reason}
                    </span>
                  )}
                </td>
              </tr>
            ))}
            {(!requests || requests.length === 0) && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-text-secondary">
                  {filter === 'pending' ? 'Geen openstaande verzoeken' : 'Geen verzoeken gevonden'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
