import { useState, useMemo } from 'react';
import { Pencil, Trash2, X, UserPlus, Building2, Users } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import {
  useInitiatief,
  useUpdateInitiatief,
  useDeleteInitiatief,
  useAddInitiatiefMember,
  useRemoveInitiatiefMember,
  useUpdateInitiatiefMemberRole,
  useAddInitiatiefEenheid,
  useRemoveInitiatiefEenheid,
  useUpdateInitiatiefEenheidRol,
} from '@/hooks/useInitiatieven';
import { usePeople } from '@/hooks/usePeople';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { INITIATIEF_COLORS, INITIATIEF_ROL_LABELS } from '@/types';
import type { InitiatiefUpdate } from '@/types';

interface InitiatiefDetailModalProps {
  initiatiefId: string;
  open: boolean;
  onClose: () => void;
}

export function InitiatiefDetailModal({
  initiatiefId,
  open,
  onClose,
}: InitiatiefDetailModalProps) {
  const { data: detail, isLoading } = useInitiatief(open ? initiatiefId : undefined);

  const [editing, setEditing] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [editForm, setEditForm] = useState<InitiatiefUpdate>({});

  const updateMutation = useUpdateInitiatief();
  const deleteMutation = useDeleteInitiatief();
  const addMemberMutation = useAddInitiatiefMember();
  const removeMemberMutation = useRemoveInitiatiefMember();
  const updateRoleMutation = useUpdateInitiatiefMemberRole();
  const addEenheidMutation = useAddInitiatiefEenheid();
  const removeEenheidMutation = useRemoveInitiatiefEenheid();
  const updateEenheidRolMutation = useUpdateInitiatiefEenheidRol();

  // Backend-resolved access level — single source of truth
  const accessLevel = detail?.access_level ?? null;
  const isEigenaar = accessLevel === 'eigenaar';
  const canEdit = accessLevel === 'eigenaar' || accessLevel === 'contributor';

  const eigenaarCount = useMemo(
    () => detail?.members.filter((m) => m.rol === 'eigenaar').length ?? 0,
    [detail],
  );

  const startEditing = () => {
    if (!detail) return;
    setEditForm({
      naam: detail.naam,
      beschrijving: detail.beschrijving,
      kleur: detail.kleur,
    });
    setEditing(true);
  };

  const handleSave = async () => {
    if (!detail) return;
    await updateMutation.mutateAsync({ id: detail.id, data: editForm });
    setEditing(false);
  };

  const handleDelete = async () => {
    if (!detail) return;
    await deleteMutation.mutateAsync(detail.id);
    setShowDeleteConfirm(false);
    onClose();
  };

  const handleClose = () => {
    setEditing(false);
    onClose();
  };

  // --- Member management ---
  const { data: allPeople = [] } = usePeople();
  const [addMemberValue, setAddMemberValue] = useState('');

  const availablePeopleOptions = useMemo(() => {
    if (!detail) return [];
    const memberIds = new Set(detail.members.map((m) => m.person_id));
    return allPeople
      .filter((p) => !memberIds.has(p.id) && !p.is_agent)
      .map((p) => ({ value: p.id, label: p.naam }));
  }, [allPeople, detail]);

  const handleAddMember = async (personId: string) => {
    if (!detail || !personId) return;
    await addMemberMutation.mutateAsync({
      initiatiefId: detail.id,
      personId,
    });
    setAddMemberValue('');
  };

  const handleRemoveMember = async (personId: string) => {
    if (!detail) return;
    await removeMemberMutation.mutateAsync({
      initiatiefId: detail.id,
      personId,
    });
  };

  const handleTransferOwnership = async (personId: string) => {
    if (!detail) return;
    await updateRoleMutation.mutateAsync({
      initiatiefId: detail.id,
      personId,
      rol: 'eigenaar',
    });
  };

  const handleDemoteToContributor = async (personId: string) => {
    if (!detail) return;
    await updateRoleMutation.mutateAsync({
      initiatiefId: detail.id,
      personId,
      rol: 'contributor',
    });
  };

  // --- Eenheid management ---
  const { data: allEenheden = [] } = useOrganisatieFlat();
  const [addEenheidValue, setAddEenheidValue] = useState('');

  const availableEenheidOptions = useMemo(() => {
    if (!detail) return [];
    const linkedEenheidIds = new Set(detail.eenheden.map((e) => e.eenheid_id));
    return allEenheden
      .filter((e) => !linkedEenheidIds.has(e.id))
      .map((e) => ({ value: e.id, label: e.naam }));
  }, [allEenheden, detail]);

  const handleAddEenheid = async (eenheidId: string) => {
    if (!detail || !eenheidId) return;
    await addEenheidMutation.mutateAsync({
      initiatiefId: detail.id,
      eenheidId,
    });
    setAddEenheidValue('');
  };

  const handleRemoveEenheid = async (eenheidId: string) => {
    if (!detail) return;
    await removeEenheidMutation.mutateAsync({
      initiatiefId: detail.id,
      eenheidId,
    });
  };

  const handleUpdateEenheidRol = async (eenheidId: string, rol: string) => {
    if (!detail) return;
    await updateEenheidRolMutation.mutateAsync({
      initiatiefId: detail.id,
      eenheidId,
      rol,
    });
  };

  const footer = (
    <>
      {isEigenaar && !editing && (
        <>
          <Button
            variant="danger"
            size="sm"
            icon={<Trash2 className="h-3.5 w-3.5" />}
            onClick={() => setShowDeleteConfirm(true)}
          >
            Verwijderen
          </Button>
          <div className="flex-1" />
        </>
      )}
      {canEdit && !editing && (
        <Button
          variant="secondary"
          size="sm"
          icon={<Pencil className="h-3.5 w-3.5" />}
          onClick={startEditing}
        >
          Bewerken
        </Button>
      )}
      {editing && (
        <>
          <Button variant="secondary" size="sm" onClick={() => setEditing(false)}>
            Annuleren
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            loading={updateMutation.isPending}
            disabled={!editForm.naam?.trim()}
          >
            Opslaan
          </Button>
        </>
      )}
      {!editing && (
        <Button variant="secondary" size="sm" onClick={handleClose}>
          Sluiten
        </Button>
      )}
    </>
  );

  return (
    <>
      <Modal
        open={open}
        onClose={handleClose}
        title={detail?.naam || 'Initiatief'}
        size="lg"
        footer={footer}
        headerIcon={
          detail?.kleur ? (
            <span
              className="inline-block h-4 w-4 rounded-full"
              style={{ backgroundColor: detail.kleur }}
            />
          ) : undefined
        }
      >
        {isLoading || !detail ? (
          <LoadingSpinner className="py-12" />
        ) : editing ? (
          <EditForm form={editForm} onChange={setEditForm} />
        ) : (
          <div className="space-y-6">
            {/* Description */}
            {detail.beschrijving && (
              <div>
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                  Beschrijving
                </h4>
                <p className="text-sm text-text whitespace-pre-wrap">
                  {detail.beschrijving}
                </p>
              </div>
            )}

            {/* Members */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
                  <Users className="h-3.5 w-3.5" />
                  Leden ({detail.members.length})
                </h4>
              </div>

              {detail.members.length > 0 && (
                <ul className="divide-y divide-border rounded-xl border border-border mb-3">
                  {detail.members.map((member) => (
                    <li
                      key={member.person_id}
                      className="flex items-center justify-between px-3 py-2"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-sm text-text truncate">
                          {member.person_naam}
                        </span>
                        <Badge variant={member.rol === 'eigenaar' ? 'purple' : 'gray'}>
                          {INITIATIEF_ROL_LABELS[member.rol] ?? member.rol}
                        </Badge>
                      </div>
                      {isEigenaar && (
                        <div className="flex items-center gap-1 shrink-0">
                          {member.rol === 'eigenaar' ? (
                            eigenaarCount > 1 && (
                              <button
                                onClick={() => handleDemoteToContributor(member.person_id)}
                                className="px-2 py-0.5 rounded text-xs text-text-secondary hover:bg-gray-100 hover:text-gray-700 transition-colors"
                                title="Maak bijdrager"
                              >
                                Maak bijdrager
                              </button>
                            )
                          ) : (
                            <>
                              <button
                                onClick={() => handleTransferOwnership(member.person_id)}
                                className="px-2 py-0.5 rounded text-xs text-text-secondary hover:bg-purple-50 hover:text-purple-600 transition-colors"
                                title="Maak eigenaar"
                              >
                                Maak eigenaar
                              </button>
                              <button
                                onClick={() => handleRemoveMember(member.person_id)}
                                className="p-1 rounded hover:bg-gray-100 text-text-secondary hover:text-red-500 transition-colors"
                                title="Verwijderen"
                              >
                                <X className="h-3.5 w-3.5" />
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}

              {isEigenaar && (
                <div className="flex items-start gap-2">
                  <div className="flex-1">
                    <CreatableSelect
                      value={addMemberValue}
                      onChange={(val) => {
                        setAddMemberValue(val);
                        if (val) handleAddMember(val);
                      }}
                      options={availablePeopleOptions}
                      placeholder="Lid toevoegen..."
                      emptyMessage="Geen personen gevonden"
                    />
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<UserPlus className="h-3.5 w-3.5" />}
                    onClick={() => {
                      if (addMemberValue) handleAddMember(addMemberValue);
                    }}
                    disabled={!addMemberValue}
                    className="mt-0.5"
                  >
                    Toevoegen
                  </Button>
                </div>
              )}
            </div>

            {/* Eenheden */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
                  <Building2 className="h-3.5 w-3.5" />
                  Organisatie-eenheden ({detail.eenheden.length})
                </h4>
              </div>

              {detail.eenheden.length > 0 && (
                <ul className="divide-y divide-border rounded-xl border border-border mb-3">
                  {detail.eenheden.map((eenheid) => (
                    <li
                      key={eenheid.eenheid_id}
                      className="flex items-center justify-between px-3 py-2"
                    >
                      <span className="text-sm text-text truncate">
                        {eenheid.eenheid_naam}
                      </span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {isEigenaar ? (
                          <select
                            value={eenheid.rol}
                            onChange={(e) => handleUpdateEenheidRol(eenheid.eenheid_id, e.target.value)}
                            className="text-xs border border-border rounded px-1.5 py-0.5 bg-white"
                          >
                            {Object.entries(INITIATIEF_ROL_LABELS).map(([value, label]) => (
                              <option key={value} value={value}>{label}</option>
                            ))}
                          </select>
                        ) : (
                          <span className="text-xs text-text-secondary bg-gray-100 rounded px-1.5 py-0.5">
                            {INITIATIEF_ROL_LABELS[eenheid.rol] ?? eenheid.rol}
                          </span>
                        )}
                        {isEigenaar && (
                          <button
                            onClick={() => handleRemoveEenheid(eenheid.eenheid_id)}
                            className="p-1 rounded hover:bg-gray-100 text-text-secondary hover:text-red-500 transition-colors"
                            title="Verwijderen"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              {isEigenaar && (
                <div className="flex items-start gap-2">
                  <div className="flex-1">
                    <CreatableSelect
                      value={addEenheidValue}
                      onChange={(val) => {
                        setAddEenheidValue(val);
                        if (val) handleAddEenheid(val);
                      }}
                      options={availableEenheidOptions}
                      placeholder="Eenheid toevoegen..."
                      emptyMessage="Geen eenheden gevonden"
                    />
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<Building2 className="h-3.5 w-3.5" />}
                    onClick={() => {
                      if (addEenheidValue) handleAddEenheid(addEenheidValue);
                    }}
                    disabled={!addEenheidValue}
                    className="mt-0.5"
                  >
                    Toevoegen
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDelete}
        title="Initiatief verwijderen"
        confirmLabel="Verwijderen"
        variant="danger"
        loading={deleteMutation.isPending}
      >
        Weet je zeker dat je <strong>{detail?.naam}</strong> wilt verwijderen? Dit kan
        niet ongedaan gemaakt worden.
      </ConfirmDialog>
    </>
  );
}

// ---------- Edit form (inline) ----------

function EditForm({
  form,
  onChange,
}: {
  form: InitiatiefUpdate;
  onChange: (form: InitiatiefUpdate) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <label className="block text-sm font-medium text-text">
          Naam <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          value={form.naam || ''}
          onChange={(e) => onChange({ ...form, naam: e.target.value })}
          className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
          autoFocus
        />
      </div>
      <div className="space-y-1.5">
        <label className="block text-sm font-medium text-text">Beschrijving</label>
        <textarea
          value={form.beschrijving || ''}
          onChange={(e) => onChange({ ...form, beschrijving: e.target.value })}
          className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 resize-none"
          rows={4}
        />
      </div>
      <div className="space-y-1.5">
        <label className="block text-sm font-medium text-text">Kleur</label>
        <div className="flex gap-2 flex-wrap">
          {INITIATIEF_COLORS.map((color) => (
            <button
              key={color}
              type="button"
              onClick={() => onChange({ ...form, kleur: color })}
              className={`h-8 w-8 rounded-full border-2 transition-all ${
                form.kleur === color
                  ? 'border-primary-500 scale-110'
                  : 'border-transparent hover:scale-105'
              }`}
              style={{ backgroundColor: color }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
