import { useCallback, useEffect, useRef, useState, useMemo } from 'react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { Badge } from '@/components/common/Badge';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { Icon } from '@/components/nldd/Icon';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { Select } from '@/components/common/Select';
import { eventValue, useNlddEvent, useNlddValue } from '@/components/nldd/events';
import {
  useInitiatief,
  useUpdateInitiatief,
  useUpdateInitiatiefSettings,
  useDeleteInitiatief,
  useAddInitiatiefMember,
  useRemoveInitiatiefMember,
  useUpdateInitiatiefMemberRole,
  useAddInitiatiefEenheid,
  useRemoveInitiatiefEenheid,
  useUpdateInitiatiefEenheidRol,
  useInitiatiefUpdates,
  useCreateInitiatiefUpdate,
  useEditInitiatiefUpdate,
  usePublishInitiatiefUpdate,
  useUnpublishInitiatiefUpdate,
  useDeleteInitiatiefUpdate,
} from '@/hooks/useInitiatieven';
import { usePeople } from '@/hooks/usePeople';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { INITIATIEF_COLORS, INITIATIEF_ROL_LABELS } from '@/types';
import type {
  Initiatief,
  InitiatiefDetail,
  InitiatiefSettingsUpdate,
  InitiatiefUpdate,
  InitiatiefUpdatePost,
} from '@/types';
import { StakeholderTab } from '@/components/stakeholders/StakeholderTab';
import { MattermostChannelsSection } from '@/components/mattermost/MattermostChannelsSection';
import { ColumnsManager } from '@/components/leads/ColumnsManager';

interface InitiatiefDetailModalProps {
  initiatiefId: string;
  open: boolean;
  onClose: () => void;
  /** z-index van deze modal (default 50). Geneste modals krijgen +10. */
  zIndex?: number;
}

export function InitiatiefDetailModal({
  initiatiefId,
  open,
  onClose,
  zIndex = 50,
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
          <Button variant="danger" size="sm" icon="trash" onClick={() => setShowDeleteConfirm(true)}>
            Verwijderen
          </Button>
          <div className="flex-1" />
        </>
      )}
      {canEdit && !editing && (
        <Button variant="secondary" size="sm" icon="pencil" onClick={startEditing}>
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
        zIndex={zIndex}
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
                <RichTextDisplay content={detail.beschrijving} />
              </div>
            )}

            {/* Members */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
                  <Icon name="users" size="sm" />
                  Leden ({detail.members.length})
                </h4>
              </div>

              {detail.members.length > 0 && (
                <nldd-list type="list" variant="box-tinted" className="mb-3">
                  {detail.members.map((member) => (
                    <nldd-list-item key={member.person_id}>
                      <div className="flex items-center justify-between w-full gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <nldd-text-cell text={member.person_naam} width="fit-content" />
                          <Badge variant={member.rol === 'eigenaar' ? 'purple' : 'gray'}>
                            {INITIATIEF_ROL_LABELS[member.rol] ?? member.rol}
                          </Badge>
                        </div>
                        {isEigenaar && (
                          <div className="flex items-center gap-1 shrink-0">
                            {member.rol === 'eigenaar' ? (
                              eigenaarCount > 1 && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleDemoteToContributor(member.person_id)}
                                >
                                  Maak bijdrager
                                </Button>
                              )
                            ) : (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleTransferOwnership(member.person_id)}
                                >
                                  Maak eigenaar
                                </Button>
                                <NlddIconButton
                                  icon="close"
                                  accessibleLabel="Verwijderen"
                                  variant="neutral-transparent"
                                  size="sm"
                                  onClick={() => handleRemoveMember(member.person_id)}
                                />
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    </nldd-list-item>
                  ))}
                </nldd-list>
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
                    icon="person-badge-plus"
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
                  <Icon name="apartment-building" size="sm" />
                  Organisatie-eenheden ({detail.eenheden.length})
                </h4>
              </div>

              {detail.eenheden.length > 0 && (
                <nldd-list type="list" variant="box-tinted" className="mb-3">
                  {detail.eenheden.map((eenheid) => (
                    <nldd-list-item key={eenheid.eenheid_id}>
                      <div className="flex items-center justify-between w-full gap-2">
                        <nldd-text-cell text={eenheid.eenheid_naam} width="fit-content" />
                        <div className="flex items-center gap-1.5 shrink-0">
                          {isEigenaar ? (
                            <Select
                              value={eenheid.rol}
                              onChange={(e) => handleUpdateEenheidRol(eenheid.eenheid_id, e.target.value)}
                              options={Object.entries(INITIATIEF_ROL_LABELS).map(([value, label]) => ({
                                value,
                                label,
                              }))}
                            />
                          ) : (
                            <nldd-tag color="neutral" size="sm" text={INITIATIEF_ROL_LABELS[eenheid.rol] ?? eenheid.rol} />
                          )}
                          {isEigenaar && (
                            <NlddIconButton
                              icon="close"
                              accessibleLabel="Verwijderen"
                              variant="neutral-transparent"
                              size="sm"
                              onClick={() => handleRemoveEenheid(eenheid.eenheid_id)}
                            />
                          )}
                        </div>
                      </div>
                    </nldd-list-item>
                  ))}
                </nldd-list>
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
                    icon="apartment-building"
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

            {/* Stakeholders */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
                  <Icon name="person" size="sm" />
                  Stakeholders
                </h4>
              </div>
              <StakeholderTab
                scopeType="initiatief"
                scopeId={detail.id}
                readOnly={!canEdit}
              />
            </div>

            {/* Mattermost-kanalen */}
            <div>
              <MattermostChannelsSection
                scope={{ type: 'initiatief', id: detail.id }}
                parentZIndex={zIndex}
              />
            </div>

            {/* Updates (publication posts) */}
            <UpdatesSection initiatief={detail} canEdit={canEdit} />

            {/* Funnel-kolommen — eigenaar only */}
            {isEigenaar && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
                    <Icon name="gear" size="sm" />
                    Funnel-kolommen
                  </h4>
                </div>
                <ColumnsManager initiatiefId={detail.id} />
              </div>
            )}

            {/* Settings — eigenaar only */}
            {isEigenaar && <SettingsSection initiatief={detail} />}
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

// ---------- Settings section (eigenaar only) ----------

function SettingsSection({ initiatief }: { initiatief: InitiatiefDetail }) {
  const settingsMutation = useUpdateInitiatiefSettings();
  const [pendingPublic, setPendingPublic] = useState(false);
  const [scoreLabels, setScoreLabels] = useState({
    score_strategisch_label: initiatief.score_strategisch_label ?? '',
    score_politiek_label: initiatief.score_politiek_label ?? '',
    score_positie_label: initiatief.score_positie_label ?? '',
  });
  const [slugDraft, setSlugDraft] = useState(initiatief.slug ?? '');
  const [slugError, setSlugError] = useState<string | null>(null);

  const save = (data: InitiatiefSettingsUpdate) =>
    settingsMutation.mutateAsync({ id: initiatief.id, data });

  const handlePublicToggle = () => {
    if (initiatief.public_page_enabled) {
      // Turning off — no confirmation needed.
      save({ public_page_enabled: false });
    } else {
      setPendingPublic(true);
    }
  };

  const confirmPublicEnable = async () => {
    await save({ public_page_enabled: true });
    setPendingPublic(false);
  };

  const persistLabels = (labels: typeof scoreLabels) => {
    save({
      score_strategisch_label: labels.score_strategisch_label || null,
      score_politiek_label: labels.score_politiek_label || null,
      score_positie_label: labels.score_positie_label || null,
    });
  };

  const publicUrl = initiatief.slug ? `/c/${initiatief.slug}` : null;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
          <Icon name="gear" size="sm" />
          Instellingen
        </h4>
      </div>

      <div className="space-y-4">
        {/* Publieke pagina */}
        <div className="space-y-3 rounded-xl border border-border p-4">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-text-secondary uppercase tracking-wider">
            <Icon name="globe" size="sm" />
            Publieke pagina
          </div>

          <ToggleRow
            icon="globe"
            label="Publieke pagina inschakelen"
            description={
              publicUrl
                ? `Pagina bereikbaar via ${publicUrl} voor iedereen met de link.`
                : 'Stel eerst een slug in om de pagina aan te kunnen zetten.'
            }
            enabled={initiatief.public_page_enabled}
            onToggle={handlePublicToggle}
            loading={settingsMutation.isPending}
            disabled={!publicUrl}
          />

          <div
            className={`space-y-1.5 ${
              initiatief.public_page_enabled || !initiatief.slug
                ? ''
                : 'opacity-60'
            }`}
          >
            <label className="block text-sm font-medium text-text">
              Slug{' '}
              <span className="text-xs text-text-secondary">
                (publieke URL-segment)
              </span>
            </label>
            {initiatief.slug ? (
              <div className="flex items-center gap-2 flex-wrap">
                {initiatief.public_page_enabled ? (
                  <nldd-link
                    href={`/c/${initiatief.slug}`}
                    target="_blank"
                    size="sm"
                    text={`/c/${initiatief.slug}`}
                    end-icon="external-link"
                  />
                ) : (
                  <code className="text-sm bg-gray-50 px-2 py-1 rounded">
                    /c/{initiatief.slug}
                  </code>
                )}
              </div>
            ) : (
              <div className="space-y-1.5">
                <p className="text-xs text-text-secondary">
                  Nog geen slug ingesteld. Kies kleine letters, cijfers en
                  streepjes (bv. <code>regelrecht</code>).
                </p>
                <div className="flex gap-2 items-start">
                  <span className="inline-flex items-center h-9 px-2 rounded-l-lg border border-r-0 border-border bg-gray-50 text-sm text-text-secondary">
                    /c/
                  </span>
                  <div className="flex-1">
                    <SlugDraftField
                      value={slugDraft}
                      onChange={(v) => {
                        setSlugDraft(v.toLowerCase());
                        setSlugError(null);
                      }}
                    />
                  </div>
                  <Button
                    size="sm"
                    onClick={async () => {
                      const trimmed = slugDraft.trim();
                      if (!trimmed) return;
                      try {
                        await save({ slug: trimmed });
                      } catch (err) {
                        const msg =
                          err instanceof Error ? err.message : 'Onbekende fout';
                        setSlugError(msg);
                      }
                    }}
                    disabled={!slugDraft.trim() || settingsMutation.isPending}
                  >
                    Instellen
                  </Button>
                </div>
                {slugError && <nldd-text size="xs" color="critical">{slugError}</nldd-text>}
              </div>
            )}
          </div>
        </div>

        {/* Funnel-afweging */}
        <div className="space-y-3 rounded-xl border border-border p-4">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-text-secondary uppercase tracking-wider">
            <Icon name="person-badge-plus" size="sm" />
            Funnel-afweging
          </div>

          <ToggleRow
            icon="person-badge-plus"
            label="Funnel-velden op leads tonen"
            description="Engagement type + drie scores (strategisch/politiek/positie) op leads in dit initiatief."
            enabled={initiatief.funnel_enabled}
            onToggle={() =>
              save({ funnel_enabled: !initiatief.funnel_enabled })
            }
            loading={settingsMutation.isPending}
          />

          {initiatief.funnel_enabled && (
            <div className="space-y-2 pt-2 border-t border-border">
              <p className="text-xs text-text-secondary">
                Optionele eigen labels voor de drie funnel-scores. Leeg laten
                gebruikt de standaard.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {(
                  [
                    ['score_strategisch_label', 'Strategisch belang'],
                    ['score_politiek_label', 'Politiek belang'],
                    ['score_positie_label', 'Positie / omgeving'],
                  ] as const
                ).map(([key, fallback]) => (
                  <label key={key} className="flex flex-col gap-0.5">
                    <span className="text-xs text-text-secondary">
                      {fallback}
                    </span>
                    <ScoreLabelField
                      value={scoreLabels[key]}
                      placeholder={fallback}
                      onCommit={(v) => {
                        const next = { ...scoreLabels, [key]: v };
                        setScoreLabels(next);
                        persistLabels(next);
                      }}
                    />
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={pendingPublic}
        onClose={() => setPendingPublic(false)}
        onConfirm={confirmPublicEnable}
        title="Publieke pagina inschakelen"
        confirmLabel="Inschakelen"
        loading={settingsMutation.isPending}
      >
        Iedereen met de link <code>/c/{initiatief.slug}</code> kan straks de
        naam, beschrijving en gepubliceerde updates van dit initiatief zien.
        Leads, scores en stakeholders blijven privé. Doorgaan?
      </ConfirmDialog>
    </div>
  );
}

/** Controlled `nldd-text-field` for the slug draft (before it is saved). */
function SlugDraftField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  return (
    <nldd-text-field
      ref={ref}
      value={value}
      placeholder="regelrecht"
      accessible-label="Slug"
      className="rounded-l-none"
    />
  );
}

/** A score-label field: value commits on `change` (blur/Enter), matching the previous onBlur-persist behaviour. */
function ScoreLabelField({
  value,
  placeholder,
  onCommit,
}: {
  value: string;
  placeholder: string;
  onCommit: (v: string) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddValue(ref, value);
  useNlddEvent(ref, 'change', useCallback((e: Event) => onCommit(eventValue(e)), [onCommit]));
  return <nldd-text-field ref={ref} size="sm" placeholder={placeholder} accessible-label={placeholder} />;
}

/**
 * A labelled row with a switch. `nldd-switch-field` has no supporting-text
 * slot for a description line, so this composes the bare `nldd-switch`
 * control with the label/description markup the row already needs, rather
 * than fighting the field variant's fixed layout.
 */
function ToggleRow({
  icon,
  label,
  description,
  enabled,
  onToggle,
  loading,
  disabled,
}: {
  icon: string;
  label: string;
  description: string;
  enabled: boolean;
  onToggle: () => void;
  loading?: boolean;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', useCallback(() => onToggle(), [onToggle]));

  return (
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-start gap-2 min-w-0">
        <Icon name={icon} size="sm" className="text-text-secondary mt-0.5" />
        <div className="min-w-0">
          <div className="text-sm font-medium text-text">{label}</div>
          <div className="text-xs text-text-secondary">{description}</div>
        </div>
      </div>
      <nldd-switch
        ref={ref}
        checked={enabled ? true : undefined}
        {...(loading || disabled ? { disabled: true } : {})}
        accessible-label={label}
        className="shrink-0"
      />
    </div>
  );
}

// ---------- Updates section (publication posts) ----------

/** Controlled `nldd-text-field` for an update post's title. */
function UpdateTitleField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddValue(ref, value);
  useNlddEvent(ref, 'input', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  return <nldd-text-field ref={ref} placeholder="Titel" accessible-label="Titel" />;
}

function UpdatesSection({
  initiatief,
  canEdit,
}: {
  initiatief: Initiatief;
  canEdit: boolean;
}) {
  const { data: posts = [] } = useInitiatiefUpdates(initiatief.id);
  const createMutation = useCreateInitiatiefUpdate();
  const editMutation = useEditInitiatiefUpdate();
  const publishMutation = usePublishInitiatiefUpdate();
  const unpublishMutation = useUnpublishInitiatiefUpdate();
  const deleteMutation = useDeleteInitiatiefUpdate();

  const [composing, setComposing] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState({ titel: '', body: '' });
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const concepts = posts.filter((p) => !p.published_at);
  const published = posts.filter((p) => p.published_at);

  const startCompose = () => {
    setDraft({ titel: '', body: '' });
    setEditingId(null);
    setComposing(true);
  };

  const startEdit = (post: InitiatiefUpdatePost) => {
    setDraft({ titel: post.titel, body: post.body ?? '' });
    setEditingId(post.id);
    setComposing(true);
  };

  const handleSave = async (publish: boolean) => {
    if (!draft.titel.trim()) return;
    if (editingId) {
      await editMutation.mutateAsync({
        initiatiefId: initiatief.id,
        postId: editingId,
        data: { titel: draft.titel, body: draft.body || null },
      });
      if (publish) {
        await publishMutation.mutateAsync({
          initiatiefId: initiatief.id,
          postId: editingId,
        });
      }
    } else {
      await createMutation.mutateAsync({
        initiatiefId: initiatief.id,
        data: { titel: draft.titel, body: draft.body || null, publish },
      });
    }
    setComposing(false);
    setEditingId(null);
  };

  const handlePublish = (post: InitiatiefUpdatePost) =>
    publishMutation.mutate({
      initiatiefId: initiatief.id,
      postId: post.id,
    });

  const handleUnpublish = (post: InitiatiefUpdatePost) =>
    unpublishMutation.mutate({
      initiatiefId: initiatief.id,
      postId: post.id,
    });

  const handleDelete = async () => {
    if (!confirmDelete) return;
    await deleteMutation.mutateAsync({
      initiatiefId: initiatief.id,
      postId: confirmDelete,
    });
    setConfirmDelete(null);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
          <Icon name="megaphone" size="sm" />
          Updates ({posts.length})
        </h4>
        {canEdit && !composing && (
          <Button variant="secondary" size="sm" onClick={startCompose}>
            Nieuwe update
          </Button>
        )}
      </div>

      {composing && (
        <div className="rounded-xl border border-border p-3 mb-3 space-y-2">
          <UpdateTitleField
            value={draft.titel}
            onChange={(v) => setDraft({ ...draft, titel: v })}
          />
          <RichTextFormField
            label="Inhoud"
            value={draft.body}
            onChange={(value) => setDraft({ ...draft, body: value })}
            rows={4}
          />
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setComposing(false);
                setEditingId(null);
              }}
            >
              Annuleren
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleSave(false)}
              disabled={!draft.titel.trim()}
            >
              Opslaan als concept
            </Button>
            <Button
              size="sm"
              onClick={() => handleSave(true)}
              disabled={!draft.titel.trim()}
            >
              {editingId ? 'Opslaan + publiceren' : 'Direct publiceren'}
            </Button>
          </div>
        </div>
      )}

      {concepts.length > 0 && (
        <div className="mb-3">
          <div className="text-xs text-text-secondary mb-1">Concepten</div>
          <nldd-list type="list" variant="box-tinted">
            {concepts.map((post) => (
              <PostRow
                key={post.id}
                post={post}
                canEdit={canEdit}
                onEdit={() => startEdit(post)}
                onPublish={() => handlePublish(post)}
                onUnpublish={() => handleUnpublish(post)}
                onDelete={() => setConfirmDelete(post.id)}
              />
            ))}
          </nldd-list>
        </div>
      )}

      {published.length > 0 ? (
        <div>
          <div className="text-xs text-text-secondary mb-1">Gepubliceerd</div>
          <nldd-list type="list" variant="box-tinted">
            {published.map((post) => (
              <PostRow
                key={post.id}
                post={post}
                canEdit={canEdit}
                onEdit={() => startEdit(post)}
                onPublish={() => handlePublish(post)}
                onUnpublish={() => handleUnpublish(post)}
                onDelete={() => setConfirmDelete(post.id)}
              />
            ))}
          </nldd-list>
        </div>
      ) : (
        concepts.length === 0 &&
        !composing && (
          <p className="text-sm text-text-secondary">
            Nog geen updates. Klik op "Nieuwe update" om iets te publiceren.
          </p>
        )
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        onClose={() => setConfirmDelete(null)}
        onConfirm={handleDelete}
        title="Update verwijderen"
        confirmLabel="Verwijderen"
        variant="danger"
        loading={deleteMutation.isPending}
      >
        Weet je zeker dat je deze update wilt verwijderen?
      </ConfirmDialog>
    </div>
  );
}

function PostRow({
  post,
  canEdit,
  onEdit,
  onPublish,
  onUnpublish,
  onDelete,
}: {
  post: InitiatiefUpdatePost;
  canEdit: boolean;
  onEdit: () => void;
  onPublish: () => void;
  onUnpublish: () => void;
  onDelete: () => void;
}) {
  const isPublished = !!post.published_at;
  return (
    <nldd-list-item>
      <div className="flex items-start justify-between gap-2 w-full py-1">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <nldd-text-cell text={post.titel} width="fit-content" />
            {isPublished ? (
              <Badge variant="green">Gepubliceerd</Badge>
            ) : (
              <Badge variant="gray">Concept</Badge>
            )}
          </div>
          {post.body && (
            <div className="mt-1 text-sm text-text-secondary line-clamp-2">
              <RichTextDisplay content={post.body} />
            </div>
          )}
          {isPublished && post.published_at && (
            <div className="mt-1 text-xs text-text-secondary">
              {new Date(post.published_at).toLocaleString('nl-NL')}
              {post.published_by_naam && ` · ${post.published_by_naam}`}
            </div>
          )}
        </div>
        {canEdit && (
          <div className="flex items-center gap-1 shrink-0">
            <NlddIconButton
              icon="pencil"
              accessibleLabel="Bewerken"
              variant="neutral-transparent"
              size="sm"
              onClick={onEdit}
            />
            {isPublished ? (
              <NlddIconButton
                icon="eye-slash"
                accessibleLabel="Terugtrekken naar concept"
                variant="neutral-transparent"
                size="sm"
                onClick={onUnpublish}
              />
            ) : (
              <NlddIconButton
                icon="eye"
                accessibleLabel="Publiceren"
                variant="neutral-transparent"
                size="sm"
                onClick={onPublish}
              />
            )}
            <NlddIconButton
              icon="trash"
              accessibleLabel="Verwijderen"
              variant="neutral-transparent"
              size="sm"
              onClick={onDelete}
            />
          </div>
        )}
      </div>
    </nldd-list-item>
  );
}

// ---------- Edit form (inline) ----------

/** Controlled `nldd-text-field` for the initiatief name, focused when the edit form opens. */
function NaamField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLElement & { focus?: () => void }>(null);
  useNlddValue(ref, value);
  useNlddEvent(ref, 'input', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  useEffect(() => {
    ref.current?.focus?.();
  }, []);
  return <nldd-text-field ref={ref} required accessible-label="Naam" />;
}

function EditForm({
  form,
  onChange,
}: {
  form: InitiatiefUpdate;
  onChange: (form: InitiatiefUpdate) => void;
}) {
  return (
    <div className="space-y-4">
      <nldd-form-field label="Naam">
        <NaamField value={form.naam || ''} onChange={(v) => onChange({ ...form, naam: v })} />
      </nldd-form-field>
      <RichTextFormField
        label="Beschrijving"
        value={form.beschrijving || ''}
        onChange={(value) => onChange({ ...form, beschrijving: value })}
        rows={4}
      />
      <div className="space-y-1.5">
        <label className="block text-sm font-medium text-text">Kleur</label>
        {/* A free-form hex swatch picker, not a semantic radio: nldd-radio-button
            renders a fixed dot glyph rather than swapping its own fill to an
            arbitrary color, so there is no nldd primitive for "a circle that IS
            the color". Left as a plain button grid. */}
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
