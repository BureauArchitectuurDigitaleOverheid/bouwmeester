import { useState, useMemo } from 'react';
import { Building2, Users, AlertTriangle } from 'lucide-react';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { useEenheidOverview } from '@/hooks/useTasks';
import { ORGANISATIE_TYPE_LABELS } from '@/types';

export function EenheidOverzichtPage() {
  const { data: eenheden } = useOrganisatieFlat();

  const [selectedEenheidId, setSelectedEenheidId] = useState<string>('');

  const eenheidOptions = useMemo(
    () =>
      (eenheden ?? []).map((e) => ({
        value: e.id,
        label: e.naam,
        description: ORGANISATIE_TYPE_LABELS[e.type] ?? e.type,
      })),
    [eenheden],
  );

  const { data: overview, isLoading, isError } = useEenheidOverview(
    selectedEenheidId || null,
  );

  return (
    <div className="space-y-6">
      {/* Org unit selector */}
      <div className="max-w-md">
        <CreatableSelect
          label="Organisatie-eenheid"
          value={selectedEenheidId}
          onChange={setSelectedEenheidId}
          options={eenheidOptions}
          placeholder="Selecteer een eenheid..."
        />
      </div>

      {!selectedEenheidId && (
        <EmptyState
          icon={<Building2 className="h-16 w-16" />}
          title="Selecteer een eenheid"
          description="Kies een organisatie-eenheid om het takenoverzicht te bekijken."
        />
      )}

      {selectedEenheidId && isLoading && (
        <LoadingSpinner className="py-8" />
      )}

      {selectedEenheidId && isError && (
        <Card>
          <div className="flex items-center gap-3 text-red-600">
            <AlertTriangle className="h-5 w-5" />
            <p className="text-sm">Kon het overzicht niet laden. Probeer het opnieuw.</p>
          </div>
        </Card>
      )}

      {selectedEenheidId && overview && (
        <div className="space-y-6">
          {/* Section 1: Onverdeeld */}
          {overview.unassigned_count > 0 && (
            <Card>
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-amber-100 text-amber-600">
                  <AlertTriangle className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-text">Onverdeeld</h2>
                  <p className="text-sm text-text-secondary">
                    {overview.unassigned_count} {overview.unassigned_count === 1 ? 'taak' : 'taken'} zonder
                    toegewezen persoon
                  </p>
                </div>
              </div>
            </Card>
          )}

          {/* Section 2: Teamoverzicht */}
          <div>
            <h2 className="text-base font-semibold text-text mb-3 flex items-center gap-2">
              <Users className="h-5 w-5 text-text-secondary" />
              Teamoverzicht
            </h2>
            {overview.by_person.length === 0 ? (
              <Card>
                <p className="text-sm text-text-secondary">
                  Geen personen in deze eenheid.
                </p>
              </Card>
            ) : (
              <Card padding={false}>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-text-secondary">
                        <th className="px-5 py-3 font-medium">Persoon</th>
                        <th className="px-5 py-3 font-medium text-right">Open</th>
                        <th className="px-5 py-3 font-medium text-right">In uitvoering</th>
                        <th className="px-5 py-3 font-medium text-right">Afgerond</th>
                        <th className="px-5 py-3 font-medium text-right">Verlopen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.by_person.map((person) => (
                        <tr
                          key={person.person_id}
                          className="border-b border-border last:border-0 hover:bg-gray-50 transition-colors"
                        >
                          <td className="px-5 py-3 font-medium text-text">
                            {person.person_naam}
                          </td>
                          <td className="px-5 py-3 text-right text-text-secondary">
                            {person.open_count}
                          </td>
                          <td className="px-5 py-3 text-right text-text-secondary">
                            {person.in_progress_count}
                          </td>
                          <td className="px-5 py-3 text-right text-text-secondary">
                            {person.done_count}
                          </td>
                          <td
                            className={`px-5 py-3 text-right font-medium ${
                              person.overdue_count > 0
                                ? 'text-red-600'
                                : 'text-text-secondary'
                            }`}
                          >
                            {person.overdue_count}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </div>

          {/* Section 3: Subeenheden */}
          {overview.by_subeenheid.length > 0 && (
            <div>
              <h2 className="text-base font-semibold text-text mb-3 flex items-center gap-2">
                <Building2 className="h-5 w-5 text-text-secondary" />
                Subeenheden
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {overview.by_subeenheid.map((sub) => (
                  <Card key={sub.eenheid_id}>
                    <div className="space-y-2">
                      <div>
                        <p className="font-medium text-text">{sub.eenheid_naam}</p>
                        <p className="text-xs text-text-secondary">
                          {ORGANISATIE_TYPE_LABELS[sub.eenheid_type] ?? sub.eenheid_type}
                        </p>
                      </div>
                      <div className="flex gap-4 text-sm text-text-secondary">
                        <span>Open: {sub.open_count}</span>
                        <span>In uitvoering: {sub.in_progress_count}</span>
                        <span>Afgerond: {sub.done_count}</span>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
