import { useCallback, useRef, useState } from 'react';
import { PersonCard } from './PersonCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { eventValue, useNlddEvent } from '@/components/nldd/events';
import type { Person } from '@/types';

interface PersonListProps {
  people: Person[];
  isLoading: boolean;
  onPersonClick?: (person: Person) => void;
}

/** The people search field: `nldd-search-field` with its `input` event bridged to React. */
function PersonSearchField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  return (
    <nldd-search-field
      ref={ref}
      value={value}
      placeholder="Zoek personen..."
      accessible-label="Zoek personen"
    />
  );
}

export function PersonList({ people, isLoading, onPersonClick }: PersonListProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredPeople = people.filter((person) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      person.naam.toLowerCase().includes(q) ||
      person.default_email?.toLowerCase().includes(q) ||
      person.email?.toLowerCase().includes(q) ||
      person.emails?.some((e) => e.email.toLowerCase().includes(q)) ||
      person.default_phone?.toLowerCase().includes(q) ||
      person.functie?.toLowerCase().includes(q) ||
      person.description?.toLowerCase().includes(q)
    );
  });

  if (isLoading) {
    return <LoadingSpinner className="py-12" />;
  }

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="max-w-sm">
        <PersonSearchField value={searchQuery} onChange={setSearchQuery} />
      </div>

      {/* Grid */}
      {filteredPeople.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredPeople.map((person) => (
            <PersonCard key={person.id} person={person} onClick={onPersonClick} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon="users"
          title="Geen personen gevonden"
          description={
            searchQuery
              ? `Geen resultaten voor "${searchQuery}".`
              : 'Er zijn nog geen personen geregistreerd.'
          }
        />
      )}
    </div>
  );
}
