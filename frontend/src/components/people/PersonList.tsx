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
    return (
      <nldd-container padding-block="48">
        <LoadingSpinner />
      </nldd-container>
    );
  }

  return (
    <nldd-container gap="16">
      <nldd-container max-width="384px">
        <PersonSearchField value={searchQuery} onChange={setSearchQuery} />
      </nldd-container>

      {filteredPeople.length > 0 ? (
        <nldd-container layout="grid" column-count={1} sm-column-count={2} lg-column-count={3} gap="16">
          {filteredPeople.map((person) => (
            <PersonCard key={person.id} person={person} onClick={onPersonClick} />
          ))}
        </nldd-container>
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
    </nldd-container>
  );
}
