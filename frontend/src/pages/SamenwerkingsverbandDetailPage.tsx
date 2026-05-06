import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Pencil, Trash2, Plus, X, Users } from 'lucide-react';
import {
  useSamenwerkingsverband,
  useUpdateSamenwerkingsverband,
  useDeleteSamenwerkingsverband,
  useAddLid,
  useRemoveLid,
} from '@/hooks/useSamenwerkingsverbanden';
import { usePeople } from '@/hooks/usePeople';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import {
  SAMENWERKINGSVERBAND_TYPE_LABELS,
  SAMENWERKINGSVERBAND_TYPE_BADGE_COLORS,
  SAMENWERKINGSVERBAND_TYPE_OPTIONS,
  type SamenwerkingsverbandUpdate,
} from '@/types';

export function SamenwerkingsverbandDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: swv, isLoading } = useSamenwerkingsverband(id ?? null);
  const updateMutation = useUpdateSamenwerkingsverband();
  const deleteMutation = useDeleteSamenwerkingsverband();
  const addLidMutation = useAddLid();
  const removeLidMutation = useRemoveLid();
  const { data: people = [] } = usePeople();

  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState<SamenwerkingsverbandUpdate>({});
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmRemoveLidId, setConfirmRemoveLidId] = useState<string | null>(null);

  // Lid-toevoeg-form
  const [showAddLid, setShowAddLid] = useState(false);
  const [newLidPersonId, setNewLidPersonId] = useState('');
  const [newLidRol, setNewLidRol] = useState('');

  if (isLoading) {
    return <div className="flex items-center justify-center py-12"><LoadingSpinner /></div>;
  }
  if (!swv || !id) {
    return (
      <div className="max-w-3xl mx-auto py-12 text-center text-text-secondary">
        Samenwerkingsverband niet gevonden.
      </div>
    );
  }

  const startEdit = () => {
    setEditForm({
      naam: swv.naam,
      type: swv.type,
      beschrijving: swv.beschrijving ?? '',
      start_datum: swv.start_datum ?? null,
      eind_datum: swv.eind_datum ?? null,
    });
    setEditing(true);
  };

  const handleSaveEdit = async () => {
    if (!id) return;
    try {
      await updateMutation.mutateAsync({ id, data: editForm });
      setEditing(false);
    } catch {
      // toast wordt al getoond
    }
  };

  const handleDelete = async () => {
    if (!id) return;
    try {
      await deleteMutation.mutateAsync(id);
      navigate('/samenwerkingsverbanden');
    } catch {
      setConfirmDelete(false);
    }
  };

  const handleAddLid = async () => {
    if (!id || !newLidPersonId) return;
    try {
      await addLidMutation.mutateAsync({
        swvId: id,
        data: {
          person_id: newLidPersonId,
          rol: newLidRol || null,
          start_datum: new Date().toISOString().slice(0, 10),
        },
      });
      setShowAddLid(false);
      setNewLidPersonId('');
      setNewLidRol('');
    } catch {
      // toast
    }
  };

  const handleRemoveLid = async () => {
    if (!id || !confirmRemoveLidId) return;
    try {
      await removeLidMutation.mutateAsync({ swvId: id, lidId: confirmRemoveLidId });
      setConfirmRemoveLidId(null);
    } catch {
      setConfirmRemoveLidId(null);
    }
  };

  const peopleAlIngedeeld = new Set(swv.leden.map((l) => l.person_id));
  const personOptions: SelectOption[] = people
    .filter((p) => p.is_active && !p.is_agent && !peopleAlIngedeeld.has(p.id))
    .sort((a, b) => a.naam.localeCompare(b.naam))
    .map((p) => {
      const parts = [p.functie, p.expertise].filter((v): v is string => !!v);
      return {
        value: p.id,
        label: p.naam,
        description: parts.length ? parts.join(' · ') : undefined,
      };
    });

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <Link
          to="/samenwerkingsverbanden"
          className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Terug naar overzicht
        </Link>
        {!editing && (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              icon={<Pencil className="h-3.5 w-3.5" />}
              onClick={startEdit}
            >
              Bewerken
            </Button>
            <Button
              variant="ghost"
              size="sm"
              icon={<Trash2 className="h-3.5 w-3.5" />}
              onClick={() => setConfirmDelete(true)}
            >
              Verwijderen
            </Button>
          </div>
        )}
      </div>

      <div className="bg-surface rounded-xl border border-border p-6">
        {editing ? (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Input
                label="Naam"
                value={editForm.naam ?? ''}
                onChange={(e) => setEditForm((f) => ({ ...f, naam: e.target.value }))}
                required
              />
              <CreatableSelect
                label="Type"
                value={editForm.type ?? swv.type}
                onChange={(v) => setEditForm((f) => ({ ...f, type: v }))}
                options={SAMENWERKINGSVERBAND_TYPE_OPTIONS}
                searchable={false}
              />
              <Input
                label="Startdatum"
                type="date"
                value={editForm.start_datum ?? ''}
                onChange={(e) =>
                  setEditForm((f) => ({ ...f, start_datum: e.target.value || null }))
                }
              />
              <Input
                label="Einddatum"
                type="date"
                value={editForm.eind_datum ?? ''}
                onChange={(e) =>
                  setEditForm((f) => ({ ...f, eind_datum: e.target.value || null }))
                }
              />
            </div>
            <RichTextFormField
              label="Beschrijving"
              value={editForm.beschrijving ?? ''}
              onChange={(v) => setEditForm((f) => ({ ...f, beschrijving: v }))}
              rows={4}
            />
            <div className="flex items-center gap-2 justify-end">
              <Button variant="secondary" onClick={() => setEditing(false)}>Annuleren</Button>
              <Button onClick={handleSaveEdit} loading={updateMutation.isPending}>Opslaan</Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h1 className="text-xl font-semibold text-text">{swv.naam}</h1>
                <div className="mt-1 flex items-center gap-2">
                  <Badge variant={SAMENWERKINGSVERBAND_TYPE_BADGE_COLORS[swv.type] ?? 'gray'}>
                    {SAMENWERKINGSVERBAND_TYPE_LABELS[swv.type] ?? swv.type}
                  </Badge>
                  <span className="text-xs text-text-secondary">
                    <Users className="inline h-3 w-3 mr-1" />
                    {swv.aantal_leden} {swv.aantal_leden === 1 ? 'lid' : 'leden'}
                  </span>
                </div>
              </div>
              <div className="text-right text-xs text-text-secondary space-y-0.5">
                {swv.start_datum && (
                  <div>Start: {new Date(swv.start_datum).toLocaleDateString('nl-NL')}</div>
                )}
                {swv.eind_datum && (
                  <div>Eind: {new Date(swv.eind_datum).toLocaleDateString('nl-NL')}</div>
                )}
              </div>
            </div>
            {swv.beschrijving && (
              <div className="pt-2 border-t border-border/60">
                <RichTextDisplay value={swv.beschrijving} />
              </div>
            )}
          </div>
        )}
      </div>

      <div className="bg-surface rounded-xl border border-border p-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-text">Leden</h2>
          <Button
            variant="ghost"
            size="sm"
            icon={<Plus className="h-3.5 w-3.5" />}
            onClick={() => setShowAddLid(true)}
          >
            Toevoegen
          </Button>
        </div>

        {showAddLid && (
          <div className="mb-4 rounded-lg border border-border bg-gray-50 p-3 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <CreatableSelect
                label="Persoon"
                value={newLidPersonId}
                onChange={setNewLidPersonId}
                options={personOptions}
                placeholder="Zoek persoon..."
              />
              <Input
                label="Rol (optioneel)"
                value={newLidRol}
                onChange={(e) => setNewLidRol(e.target.value)}
                placeholder="bv. trekker, voorzitter"
              />
            </div>
            <div className="flex items-center gap-2 justify-end">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => { setShowAddLid(false); setNewLidPersonId(''); setNewLidRol(''); }}
              >
                Annuleren
              </Button>
              <Button
                size="sm"
                onClick={handleAddLid}
                loading={addLidMutation.isPending}
                disabled={!newLidPersonId}
              >
                Toevoegen
              </Button>
            </div>
          </div>
        )}

        {swv.leden.length === 0 ? (
          <p className="text-sm text-text-secondary italic">Nog geen leden.</p>
        ) : (
          <ul className="space-y-1">
            {swv.leden.map((lid) => (
              <li
                key={lid.id}
                className="group flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-gray-50 transition-colors"
              >
                <div className="flex-1 flex items-center gap-2 text-sm">
                  <span className="font-medium text-text">{lid.person_naam}</span>
                  {lid.person_expertise && (
                    <Badge variant="indigo">{lid.person_expertise}</Badge>
                  )}
                  {lid.rol && (
                    <span className="text-xs text-text-secondary">— {lid.rol}</span>
                  )}
                </div>
                <span className="text-xs text-text-secondary">
                  sinds {new Date(lid.start_datum).toLocaleDateString('nl-NL')}
                </span>
                <button
                  onClick={() => setConfirmRemoveLidId(lid.id)}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded text-text-secondary hover:text-red-600 hover:bg-red-50 transition-all"
                  title="Verwijderen"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={handleDelete}
        title="Samenwerkingsverband verwijderen"
        confirmLabel="Verwijderen"
        variant="danger"
        loading={deleteMutation.isPending}
      >
        <p>
          Weet je zeker dat je <strong>{swv.naam}</strong> wilt verwijderen? Alle
          lidmaatschappen worden meegenomen.
        </p>
      </ConfirmDialog>

      <ConfirmDialog
        open={!!confirmRemoveLidId}
        onClose={() => setConfirmRemoveLidId(null)}
        onConfirm={handleRemoveLid}
        title="Lid verwijderen"
        confirmLabel="Verwijderen"
        variant="danger"
        loading={removeLidMutation.isPending}
      >
        <p>Weet je zeker dat je dit lid wilt verwijderen?</p>
      </ConfirmDialog>
    </div>
  );
}
