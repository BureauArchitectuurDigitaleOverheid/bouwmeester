import { useState } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { useCreatePerson } from '@/hooks/usePeople';
import { useOrganisatieFlat, useCreateOrganisatieEenheid } from '@/hooks/useOrganisatie';

interface PersonQuickCreateFormProps {
  open: boolean;
  onClose: () => void;
  initialName: string;
  onCreated: (personId: string) => void;
}

export function PersonQuickCreateForm({
  open,
  onClose,
  initialName,
  onCreated,
}: PersonQuickCreateFormProps) {
  const [naam, setNaam] = useState(initialName);
  const [email, setEmail] = useState('');
  const [organisatieEenheidId, setOrganisatieEenheidId] = useState('');
  const createPerson = useCreatePerson();
  const { data: orgEenheden = [] } = useOrganisatieFlat();
  const createOrgMutation = useCreateOrganisatieEenheid();

  const orgOptions = orgEenheden.map((e) => ({
    value: e.id,
    label: e.naam,
    description: e.type,
  }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!naam.trim()) return;

    const person = await createPerson.mutateAsync({
      naam: naam.trim(),
      email: email.trim() || undefined,
      organisatie_eenheid_id: organisatieEenheidId || undefined,
    });

    onCreated(person.id);
    setNaam('');
    setEmail('');
    setOrganisatieEenheidId('');
    onClose();
  };

  const handleCreateOrgEenheid = async (text: string): Promise<string | null> => {
    try {
      const result = await createOrgMutation.mutateAsync({
        naam: text,
        type: 'afdeling',
      });
      return result.id;
    } catch {
      return null;
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Persoon snel aanmaken"
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuleren
          </Button>
          <Button
            onClick={handleSubmit}
            loading={createPerson.isPending}
            disabled={!naam.trim()}
          >
            Aanmaken
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Naam"
          value={naam}
          onChange={(e) => setNaam(e.target.value)}
          placeholder="Volledige naam"
          required
          autoFocus
        />
        <Input
          label="E-mail"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email@voorbeeld.nl"
        />
        <CreatableSelect
          label="Organisatie-eenheid"
          value={organisatieEenheidId}
          onChange={setOrganisatieEenheidId}
          options={orgOptions}
          placeholder="Selecteer of maak eenheid..."
          onCreate={handleCreateOrgEenheid}
          createLabel="Nieuwe eenheid aanmaken"
        />
      </form>
    </Modal>
  );
}
