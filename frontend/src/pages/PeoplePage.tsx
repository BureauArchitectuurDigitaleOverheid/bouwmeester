import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { PersonList } from '@/components/people/PersonList';
import { PersonEditForm } from '@/components/people/PersonEditForm';
import { usePeople } from '@/hooks/usePeople';
import { usePersonFormSubmit } from '@/hooks/usePersonFormSubmit';
import type { Person } from '@/types';

export function PeoplePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [showForm, setShowForm] = useState(false);
  const [editPerson, setEditPerson] = useState<Person | null>(null);

  const { data: people = [], isLoading } = usePeople();

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
  const { handleSubmit: handleFormSubmit, isPending } = usePersonFormSubmit(() => setShowForm(false));

  const handleAddPerson = () => {
    setEditPerson(null);
    setShowForm(true);
  };

  const handleEditPerson = (person: Person) => {
    setEditPerson(person);
    setShowForm(true);
  };

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-text-secondary">
            Overzicht van alle betrokken personen.
          </p>
        </div>
        <Button
          icon={<Plus className="h-4 w-4" />}
          onClick={handleAddPerson}
        >
          Persoon toevoegen
        </Button>
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
        onClose={() => setShowForm(false)}
        onSubmit={handleFormSubmit}
        isLoading={isPending}
        editData={editPerson}
      />
    </div>
  );
}
