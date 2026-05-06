import { useState } from 'react';
import { Plus, X, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  useSamenwerkingsverbanden,
  useCreateSamenwerkingsverband,
} from '@/hooks/useSamenwerkingsverbanden';
import { Badge } from '@/components/common/Badge';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import {
  SAMENWERKINGSVERBAND_TYPE_LABELS,
  SAMENWERKINGSVERBAND_TYPE_BADGE_COLORS,
  SAMENWERKINGSVERBAND_TYPE_OPTIONS,
  type SamenwerkingsverbandCreate,
} from '@/types';

const ALL_TYPE_OPTIONS: SelectOption[] = [
  { value: '', label: 'Alle types' },
  ...SAMENWERKINGSVERBAND_TYPE_OPTIONS,
];

export function SamenwerkingsverbandenPage() {
  const [typeFilter, setTypeFilter] = useState('');
  const [actiefOnly, setActiefOnly] = useState(true);
  const [search, setSearch] = useState('');
  const { data = [], isLoading } = useSamenwerkingsverbanden({
    type: typeFilter || undefined,
    actief: actiefOnly ? true : undefined,
    search: search || undefined,
  });
  const createMutation = useCreateSamenwerkingsverband();

  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<SamenwerkingsverbandCreate>({
    naam: '',
    type: 'programma',
  });

  const resetForm = () => {
    setForm({ naam: '', type: 'programma' });
    setError(null);
    setShowForm(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await createMutation.mutateAsync(form);
      resetForm();
    } catch {
      setError('Fout bij aanmaken samenwerkingsverband.');
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-64">
            <Input
              label="Zoeken"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Naam..."
            />
          </div>
          <div className="w-48">
            <CreatableSelect
              label="Type"
              value={typeFilter}
              onChange={setTypeFilter}
              options={ALL_TYPE_OPTIONS}
              searchable={false}
            />
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm text-text-secondary">
            <input
              type="checkbox"
              checked={actiefOnly}
              onChange={(e) => setActiefOnly(e.target.checked)}
              className="rounded border-border"
            />
            Alleen actieve
          </label>
        </div>
        <Button
          variant="primary"
          icon={<Plus className="h-4 w-4" />}
          onClick={() => { resetForm(); setShowForm(true); }}
        >
          Nieuw samenwerkingsverband
        </Button>
      </div>

      {showForm && (
        <div className="bg-surface rounded-xl border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text">Nieuw samenwerkingsverband</h3>
            <button onClick={resetForm} className="text-text-secondary hover:text-text transition-colors">
              <X className="h-4 w-4" />
            </button>
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Input
                label="Naam"
                value={form.naam}
                onChange={(e) => setForm((f) => ({ ...f, naam: e.target.value }))}
                required
                autoFocus
              />
              <CreatableSelect
                label="Type"
                value={form.type}
                onChange={(v) => setForm((f) => ({ ...f, type: v }))}
                options={SAMENWERKINGSVERBAND_TYPE_OPTIONS}
                searchable={false}
              />
              <Input
                label="Startdatum"
                type="date"
                value={form.start_datum ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, start_datum: e.target.value || null }))}
              />
              <Input
                label="Einddatum"
                type="date"
                value={form.eind_datum ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, eind_datum: e.target.value || null }))}
              />
            </div>
            <RichTextFormField
              label="Beschrijving"
              value={form.beschrijving ?? ''}
              onChange={(v) => setForm((f) => ({ ...f, beschrijving: v }))}
              rows={3}
            />
            {error && <p className="text-sm text-red-600">{error}</p>}
            <div className="flex items-center gap-2 justify-end">
              <Button variant="secondary" onClick={resetForm} type="button">Annuleren</Button>
              <Button type="submit" loading={createMutation.isPending}>Aanmaken</Button>
            </div>
          </form>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-12"><LoadingSpinner /></div>
      ) : data.length === 0 ? (
        <div className="text-center py-12 text-text-secondary">
          Geen samenwerkingsverbanden gevonden.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {data.map((swv) => (
            <Link
              key={swv.id}
              to={`/samenwerkingsverbanden/${swv.id}`}
              className="block rounded-xl border border-border bg-surface p-4 hover:border-primary-300 hover:shadow-sm transition-all"
            >
              <div className="flex items-center justify-between mb-2">
                <Badge variant={SAMENWERKINGSVERBAND_TYPE_BADGE_COLORS[swv.type] ?? 'gray'}>
                  {SAMENWERKINGSVERBAND_TYPE_LABELS[swv.type] ?? swv.type}
                </Badge>
                <div className="flex items-center gap-1 text-xs text-text-secondary">
                  <Users className="h-3 w-3" />
                  {swv.aantal_leden}
                </div>
              </div>
              <h3 className="text-sm font-semibold text-text truncate">{swv.naam}</h3>
              {swv.eind_datum && (
                <p className="mt-1 text-xs text-text-secondary">
                  Eindigt {new Date(swv.eind_datum).toLocaleDateString('nl-NL')}
                </p>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
