import { useState, useEffect, useMemo } from 'react';
import { Building2, Users, AlertTriangle } from 'lucide-react';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { UnassignedTasksSection } from '@/components/eenheid/UnassignedTasksSection';
import { PersonTasksRow } from '@/components/eenheid/PersonTasksRow';
import { SubeenheidCard } from '@/components/eenheid/SubeenheidCard';
import { useOrganisatieFlat, useManagedEenheden } from '@/hooks/useOrganisatie';
import { useEenheidOverview } from '@/hooks/useTasks';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { ORGANISATIE_TYPE_LABELS } from '@/types';

export function EenheidOverzichtPage() {
  const { currentPerson } = useCurrentPerson();
  const { data: managedEenheden } = useManagedEenheden(currentPerson?.id);
  const { data: eenheden } = useOrganisatieFlat();

  const [selectedEenheidId, setSelectedEenheidId] = useState<string>('');
  const [expandedPersonId, setExpandedPersonId] = useState<string | null>(null);

  const eenheidOptions = useMemo(
    () =>
      (eenheden ?? []).map((e) => ({
        value: e.id,
        label: e.naam,
        description: ORGANISATIE_TYPE_LABELS[e.type] ?? e.type,
      })),
    [eenheden],
  );

  // Auto-select managed unit on load
  useEffect(() => {
    if (selectedEenheidId) return;
    if (managedEenheden && managedEenheden.length > 0) {
      setSelectedEenheidId(managedEenheden[0].id);
    }
  }, [managedEenheden, selectedEenheidId]);

  const { data: overview, isLoading, isError } = useEenheidOverview(
    selectedEenheidId || null,
  );

  const handleSelectSubeenheid = (eenheidId: string) => {
    setSelectedEenheidId(eenheidId);
    setExpandedPersonId(null);
  };

  const handleTogglePerson = (personId: string) => {
    setExpandedPersonId((prev) => (prev === personId ? null : personId));
  };

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
          <UnassignedTasksSection
            noUnitTasks={overview.unassigned_no_unit}
            noUnitCount={overview.unassigned_no_unit_count}
            noPersonTasks={overview.unassigned_no_person}
            noPersonCount={overview.unassigned_no_person_count}
            eenheidType={overview.eenheid_type}
            selectedEenheidId={selectedEenheidId}
          />

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
                        <th className="px-3 md:px-5 py-3 font-medium">Persoon</th>
                        <th className="px-3 md:px-5 py-3 font-medium text-right">Open</th>
                        <th className="px-3 md:px-5 py-3 font-medium text-right">In uitvoering</th>
                        <th className="px-3 md:px-5 py-3 font-medium text-right">Afgerond</th>
                        <th className="px-3 md:px-5 py-3 font-medium text-right">Verlopen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.by_person.map((person) => (
                        <PersonTasksRow
                          key={person.person_id}
                          person={person}
                          isExpanded={expandedPersonId === person.person_id}
                          onToggle={() => handleTogglePerson(person.person_id)}
                        />
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
                  <SubeenheidCard
                    key={sub.eenheid_id}
                    sub={sub}
                    onSelect={handleSelectSubeenheid}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
