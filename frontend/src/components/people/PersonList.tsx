import { useState } from 'react';
import { Search, Users } from 'lucide-react';
import { PersonCard } from './PersonCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { Input } from '@/components/common/Input';
import type { Person } from '@/types';

interface PersonListProps {
  people: Person[];
  isLoading: boolean;
  onPersonClick?: (person: Person) => void;
}

export function PersonList({ people, isLoading, onPersonClick }: PersonListProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredPeople = people.filter((person) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      person.naam.toLowerCase().includes(q) ||
      person.email?.toLowerCase().includes(q) ||
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
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
        <Input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Zoek personen..."
          className="pl-9"
        />
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
          icon={<Users className="h-16 w-16" />}
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
