import { useState, useEffect } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { useCreatePerson } from '@/hooks/usePeople';

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
  const createPerson = useCreatePerson();

  useEffect(() => {
    if (open) {
      setNaam(initialName);
      setEmail('');
    }
  }, [open, initialName]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!naam.trim()) return;

    const person = await createPerson.mutateAsync({
      naam: naam.trim(),
      email: email.trim() || undefined,
    });

    onCreated(person.id);
    setNaam('');
    setEmail('');
    onClose();
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
      </form>
    </Modal>
  );
}
