import { useCallback, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  useSamenwerkingsverband,
  useUpdateSamenwerkingsverband,
  useDeleteSamenwerkingsverband,
  useAddLid,
  useUpdateLid,
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
import { PersonQuickCreateForm } from '@/components/people/PersonQuickCreateForm';
import { Icon } from '@/components/nldd/Icon';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { useNlddEvent } from '@/components/nldd/events';
import {
  SAMENWERKINGSVERBAND_TYPE_LABELS,
  SAMENWERKINGSVERBAND_TYPE_BADGE_COLORS,
  SAMENWERKINGSVERBAND_TYPE_OPTIONS,
  type SamenwerkingsverbandLid,
  type SamenwerkingsverbandLidUpdate,
  type SamenwerkingsverbandUpdate,
} from '@/types';

/** True when the click asked for something other than plain navigation. */
function isModifiedClick(event: MouseEvent): boolean {
  return event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button === 1;
}

/** `nldd-link` that navigates through the router instead of a full page load. */
function BackLink({ to, text }: { to: string; text: string }) {
  const ref = useRef<HTMLElement>(null);
  const navigate = useNavigate();
  const onClick = useCallback(
    (event: Event) => {
      const mouse = event as MouseEvent;
      if (isModifiedClick(mouse)) return;
      event.preventDefault();
      navigate(to);
    },
    [navigate, to],
  );
  useNlddEvent(ref, 'click', onClick);
  return <nldd-link ref={ref} href={to} size="sm" start-icon="arrow-left" text={text} />;
}

export function SamenwerkingsverbandDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: swv, isLoading } = useSamenwerkingsverband(id ?? null);
  const updateMutation = useUpdateSamenwerkingsverband();
  const deleteMutation = useDeleteSamenwerkingsverband();
  const addLidMutation = useAddLid();
  const updateLidMutation = useUpdateLid();
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

  // Inline persoon-aanmaken vanuit lid-toevoeg-flow
  const [showPersonCreate, setShowPersonCreate] = useState(false);
  const [personCreateName, setPersonCreateName] = useState('');

  // Lid-bewerken-form (één lid tegelijk)
  const [editingLidId, setEditingLidId] = useState<string | null>(null);
  const [lidEditForm, setLidEditForm] = useState<{
    rol: string;
    start_datum: string;
    eind_datum: string;
  }>({ rol: '', start_datum: '', eind_datum: '' });

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

  const handleCreatePerson = async (text: string): Promise<string | null> => {
    setPersonCreateName(text);
    setShowPersonCreate(true);
    return null;
  };

  const handlePersonCreated = (personId: string) => {
    setNewLidPersonId(personId);
  };

  const startEditLid = (lid: SamenwerkingsverbandLid) => {
    setEditingLidId(lid.id);
    setLidEditForm({
      rol: lid.rol ?? '',
      start_datum: lid.start_datum ?? '',
      eind_datum: lid.eind_datum ?? '',
    });
  };

  const cancelEditLid = () => {
    setEditingLidId(null);
  };

  const handleSaveLid = async () => {
    if (!id || !editingLidId) return;
    const data: SamenwerkingsverbandLidUpdate = {
      rol: lidEditForm.rol.trim() || null,
      eind_datum: lidEditForm.eind_datum || null,
    };
    // Lege start_datum niet meesturen: kolom is NOT NULL en er is geen
    // semantische "lid sinds onbekend"-state. Veld blijft dan onveranderd.
    if (lidEditForm.start_datum) {
      data.start_datum = lidEditForm.start_datum;
    }
    try {
      await updateLidMutation.mutateAsync({ swvId: id, lidId: editingLidId, data });
      setEditingLidId(null);
    } catch {
      // toast
    }
  };

  const peopleAlIngedeeld = new Set(swv.leden.map((l) => l.person_id));
  const personOptions: SelectOption[] = people
    .filter((p) => p.is_active && !p.is_agent && !peopleAlIngedeeld.has(p.id))
    .sort((a, b) => a.naam.localeCompare(b.naam))
    .map((p) => ({
      value: p.id,
      label: p.naam,
      description: p.functie ?? undefined,
    }));

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <BackLink to="/samenwerkingsverbanden" text="Terug naar overzicht" />
        {!editing && (
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" icon="pencil" onClick={startEdit}>
              Bewerken
            </Button>
            <Button
              variant="ghost"
              size="sm"
              icon="trash"
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
                  <span className="text-xs text-text-secondary inline-flex items-center gap-1">
                    <Icon name="users" size="xs" />
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
                <RichTextDisplay content={swv.beschrijving} />
              </div>
            )}
          </div>
        )}
      </div>

      <div className="bg-surface rounded-xl border border-border p-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-text">Leden</h2>
          <Button variant="ghost" size="sm" icon="plus" onClick={() => setShowAddLid(true)}>
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
                onCreate={handleCreatePerson}
                createLabel="Nieuwe persoon aanmaken"
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
          <nldd-inline-dialog text="Nog geen leden." />
        ) : (
          <nldd-list type="list" variant="box-tinted">
            {swv.leden.map((lid) => {
              const isEditing = editingLidId === lid.id;
              if (isEditing) {
                return (
                  <nldd-list-item key={lid.id}>
                    <div className="w-full py-2 space-y-3">
                      <div className="text-sm font-medium text-text">{lid.person_naam}</div>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <Input
                          label="Rol"
                          value={lidEditForm.rol}
                          onChange={(e) =>
                            setLidEditForm((f) => ({ ...f, rol: e.target.value }))
                          }
                          placeholder="bv. trekker, voorzitter"
                        />
                        <Input
                          label="Startdatum"
                          type="date"
                          value={lidEditForm.start_datum}
                          onChange={(e) =>
                            setLidEditForm((f) => ({ ...f, start_datum: e.target.value }))
                          }
                        />
                        <Input
                          label="Einddatum"
                          type="date"
                          value={lidEditForm.eind_datum}
                          onChange={(e) =>
                            setLidEditForm((f) => ({ ...f, eind_datum: e.target.value }))
                          }
                        />
                      </div>
                      <div className="flex items-center gap-2 justify-end">
                        <Button variant="secondary" size="sm" onClick={cancelEditLid}>
                          Annuleren
                        </Button>
                        <Button
                          size="sm"
                          onClick={handleSaveLid}
                          loading={updateLidMutation.isPending}
                        >
                          Opslaan
                        </Button>
                      </div>
                    </div>
                  </nldd-list-item>
                );
              }
              return (
                <nldd-list-item key={lid.id} className="group">
                  <div className="flex items-center gap-2 w-full">
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
                      {lid.eind_datum && (
                        <> · tot {new Date(lid.eind_datum).toLocaleDateString('nl-NL')}</>
                      )}
                    </span>
                    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <NlddIconButton
                        icon="pencil"
                        accessibleLabel="Bewerken"
                        variant="neutral-transparent"
                        size="sm"
                        onClick={() => startEditLid(lid)}
                      />
                      <NlddIconButton
                        icon="close"
                        accessibleLabel="Verwijderen"
                        variant="neutral-transparent"
                        size="sm"
                        onClick={() => setConfirmRemoveLidId(lid.id)}
                      />
                    </div>
                  </div>
                </nldd-list-item>
              );
            })}
          </nldd-list>
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

      <PersonQuickCreateForm
        open={showPersonCreate}
        onClose={() => setShowPersonCreate(false)}
        initialName={personCreateName}
        onCreated={handlePersonCreated}
      />
    </div>
  );
}
