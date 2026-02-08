import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { PersonList } from '@/components/people/PersonList';
import { PersonEditForm } from '@/components/people/PersonEditForm';
import { usePeople, useCreatePerson, useUpdatePerson, useAddPersonOrganisatie } from '@/hooks/usePeople';
import type { Person, PersonCreate } from '@/types';

export function PeoplePage() {
  const [showForm, setShowForm] = useState(false);
  const [editPerson, setEditPerson] = useState<Person | null>(null);

  const { data: people = [], isLoading } = usePeople();
  const createPersonMutation = useCreatePerson();
  const updatePersonMutation = useUpdatePerson();
  const addPlacementMutation = useAddPersonOrganisatie();

  const handleAddPerson = () => {
    setEditPerson(null);
    setShowForm(true);
  };

  const handleEditPerson = (person: Person) => {
    setEditPerson(person);
    setShowForm(true);
  };

  const handleFormSubmit = (data: PersonCreate, orgEenheidId?: string) => {
    if (editPerson) {
      updatePersonMutation.mutate(
        { id: editPerson.id, data },
        { onSuccess: () => setShowForm(false) },
      );
    } else {
      createPersonMutation.mutate(data, {
        onSuccess: (person) => {
          if (orgEenheidId) {
            addPlacementMutation.mutate({
              personId: person.id,
              data: {
                organisatie_eenheid_id: orgEenheidId,
                dienstverband: 'in_dienst',
                start_datum: new Date().toISOString().split('T')[0],
              },
            });
          }
          setShowForm(false);
        },
      });
    }
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
        isLoading={createPersonMutation.isPending || updatePersonMutation.isPending}
        editData={editPerson}
      />
    </div>
  );
}
