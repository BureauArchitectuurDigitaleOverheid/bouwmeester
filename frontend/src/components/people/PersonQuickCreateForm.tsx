import { useState, useEffect } from 'react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Button } from '@/components/common/Button';
import { useCreatePerson } from '@/hooks/usePeople';
import { searchPeople } from '@/api/people';
import { useDebounce } from '@/hooks/useDebounce';

interface DuplicateHit {
  id: string;
  naam: string;
  email?: string | null;
  functie?: string | null;
}

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
  const [duplicates, setDuplicates] = useState<DuplicateHit[]>([]);
  const [searching, setSearching] = useState(false);
  const createPerson = useCreatePerson();

  const debouncedNaam = useDebounce(naam.trim(), 400);

  useEffect(() => {
    if (open) {
      setNaam(initialName);
      setEmail('');
      setDuplicates([]);
    }
  }, [open, initialName]);

  // Search for existing persons when name changes
  useEffect(() => {
    if (!debouncedNaam || debouncedNaam.length < 2) {
      setDuplicates([]);
      return;
    }
    let cancelled = false;
    setSearching(true);
    searchPeople(debouncedNaam, 5)
      .then((results) => {
        if (!cancelled) {
          setDuplicates(
            results.map((p) => ({
              id: p.id,
              naam: p.naam,
              email: p.default_email ?? p.email,
              functie: p.functie,
            })),
          );
          setSearching(false);
        }
      })
      .catch(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedNaam]);

  const doCreate = async (force: boolean) => {
    if (!naam.trim()) return;
    try {
      const person = await createPerson.mutateAsync({
        naam: naam.trim(),
        email: email.trim() || undefined,
        force,
      });
      onCreated(person.id);
      setNaam('');
      setEmail('');
      onClose();
    } catch {
      // Error toast already shown by useMutationWithError
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    doCreate(duplicates.length > 0);
  };

  const handleSelectExisting = (personId: string) => {
    onCreated(personId);
    setNaam('');
    setEmail('');
    onClose();
  };

  const hasDuplicates = duplicates.length > 0;

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
          {hasDuplicates ? (
            <Button
              onClick={() => doCreate(true)}
              loading={createPerson.isPending}
              disabled={!naam.trim()}
              variant="secondary"
            >
              Toch aanmaken
            </Button>
          ) : (
            <Button
              onClick={() => doCreate(false)}
              loading={createPerson.isPending}
              disabled={!naam.trim()}
            >
              Aanmaken
            </Button>
          )}
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

        {searching && (
          <p className="text-sm text-gray-500">Zoeken naar bestaande personen...</p>
        )}

        {hasDuplicates && !searching && (
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3">
            <p className="text-sm font-medium text-amber-800 mb-2">
              Er bestaan al personen met een vergelijkbare naam:
            </p>
            <ul className="space-y-1">
              {duplicates.map((d) => (
                <li key={d.id} className="flex items-center justify-between text-sm">
                  <span className="text-gray-900">
                    {d.naam}
                    {d.email && (
                      <span className="text-gray-500 ml-1">({d.email})</span>
                    )}
                    {d.functie && (
                      <span className="text-gray-500 ml-1">- {d.functie}</span>
                    )}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleSelectExisting(d.id)}
                    className="ml-2 text-indigo-600 hover:text-indigo-800 font-medium whitespace-nowrap"
                  >
                    Selecteer
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </form>
    </Modal>
  );
}
