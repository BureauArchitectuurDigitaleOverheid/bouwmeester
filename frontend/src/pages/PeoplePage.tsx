import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PersonList } from '@/components/people/PersonList';
import { PersonEditForm } from '@/components/people/PersonEditForm';
import { NlddButton } from '@/components/nldd/NlddLink';
import { usePeople } from '@/hooks/usePeople';
import { usePersonFormSubmit } from '@/hooks/usePersonFormSubmit';
import type { Person } from '@/types';

export function PeoplePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [showForm, setShowForm] = useState(false);
  const [editPerson, setEditPerson] = useState<Person | null>(null);
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null);

  const { data: people = [], isLoading } = usePeople({ refetchInterval: 60_000 });

  // Open person detail when navigated via ?person={id}
  useEffect(() => {
    const personParam = searchParams.get('person');
    if (personParam && people.length > 0) {
      const match = people.find((p) => p.id === personParam);
      if (match) {
        setEditPerson(match);
        setShowForm(true);
      }
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams, people]);

  const { handleSubmit: handleFormSubmit, isPending } = usePersonFormSubmit(
    () => {
      setShowForm(false);
      setCreatedApiKey(null);
    },
    (person) => {
      // Capture one-time API key from agent creation response
      if (person.api_key && person.is_agent) {
        setCreatedApiKey(person.api_key);
        setEditPerson(person);
      }
    },
  );

  const handleAddPerson = () => {
    setEditPerson(null);
    setCreatedApiKey(null);
    setShowForm(true);
  };

  const handleEditPerson = (person: Person) => {
    setEditPerson(person);
    setCreatedApiKey(null);
    setShowForm(true);
  };

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <nldd-text color="secondary">Overzicht van alle betrokken personen.</nldd-text>
        <div className="flex items-center gap-2 shrink-0">
          <NlddButton text="Persoon toevoegen" startIcon="plus" onClick={handleAddPerson} />
        </div>
      </div>

      {/* People list */}
      <PersonList
        people={people}
        isLoading={isLoading}
        onPersonClick={handleEditPerson}
      />

      {/* Create/Edit person form */}
      <PersonEditForm
        open={showForm}
        onClose={() => {
          setShowForm(false);
          setCreatedApiKey(null);
        }}
        onSubmit={handleFormSubmit}
        isLoading={isPending}
        editData={editPerson}
        createdApiKey={createdApiKey}
      />
    </div>
  );
}
