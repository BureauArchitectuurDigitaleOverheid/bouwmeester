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
import { eventValue, orUndef, useNlddEvent, useNlddValue } from '@/components/nldd/events';
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
import { INITIATIEF_ROL_LABELS } from '@/types';
import { InitiatiefKleurPicker } from './InitiatiefKleurPicker';
import { initiatiefIconColor } from './initiatiefColors';
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
}

/**
 * A section heading: an icon and an `<h4>` in `nldd-title`'s slot, sized to sit
 * in a row with an action button on the right.
 *
 * `width="fit-content"` plus `row-fill`, rather than the container default:
 * that default is `width: full`, which takes a hard 100% of the row and leaves
 * the button less room than its own label needs. The label then wraps and the
 * button becomes a two-line block half again as tall as it should be.
 */
function SectionHeading({ icon, text }: { icon: string; text: string }) {
  return (
    <nldd-container
      layout="row"
      width="fit-content"
      className="row-fill"
      gap="6"
      vertical-alignment="center"
    >
      <Icon name={icon} size="sm" />
      <nldd-title size={4}>
        <h4>{text}</h4>
      </nldd-title>
    </nldd-container>
  );
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
          <Button variant="danger" size="sm" icon="trash" onClick={() => setShowDeleteConfirm(true)}>
            Verwijderen
          </Button>
          <nldd-container width="full" />
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
        footer={footer}
        headerIcon={
          detail?.kleur ? (
            <nldd-icon name="circle-filled" size="16" color={initiatiefIconColor(detail.kleur)} />
          ) : undefined
        }
      >
        {isLoading || !detail ? (
          <LoadingSpinner padding="48" />
        ) : editing ? (
          <EditForm form={editForm} onChange={setEditForm} />
        ) : (
          <nldd-container gap="24">
            {/* Description */}
            {detail.beschrijving && (
              <nldd-container gap="4">
                <nldd-text size="xs" weight="bold" color="secondary">
                  Beschrijving
                </nldd-text>
                <RichTextDisplay content={detail.beschrijving} />
              </nldd-container>
            )}

            {/* Members */}
            <nldd-container gap="8">
              <SectionHeading icon="users" text={`Leden (${detail.members.length})`} />

              {detail.members.length > 0 && (
                <nldd-list type="list" variant="box-tinted">
                  {detail.members.map((member) => (
                    <nldd-list-item key={member.person_id}>
                      <nldd-container layout="row" width="full" gap="8" horizontal-alignment="right" vertical-alignment="center">
                        <nldd-container layout="row" gap="8" vertical-alignment="center">
                          <nldd-text-cell text={member.person_naam} width="fit-content" />
                          <Badge variant={member.rol === 'eigenaar' ? 'purple' : 'gray'}>
                            {INITIATIEF_ROL_LABELS[member.rol] ?? member.rol}
                          </Badge>
                        </nldd-container>
                        {isEigenaar && (
                          <nldd-container layout="row" gap="4" vertical-alignment="center">
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
                          </nldd-container>
                        )}
                      </nldd-container>
                    </nldd-list-item>
                  ))}
                </nldd-list>
              )}

              {isEigenaar && (
                <nldd-container layout="row" gap="8" vertical-alignment="top">
                  <nldd-container width="fit-content" className="row-fill">
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
                  </nldd-container>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon="person-badge-plus"
                    onClick={() => {
                      if (addMemberValue) handleAddMember(addMemberValue);
                    }}
                    disabled={!addMemberValue}
                  >
                    Toevoegen
                  </Button>
                </nldd-container>
              )}
            </nldd-container>

            {/* Eenheden */}
            <nldd-container gap="8">
              <SectionHeading icon="apartment-building" text={`Organisatie-eenheden (${detail.eenheden.length})`} />

              {detail.eenheden.length > 0 && (
                <nldd-list type="list" variant="box-tinted">
                  {detail.eenheden.map((eenheid) => (
                    <nldd-list-item key={eenheid.eenheid_id}>
                      <nldd-container layout="row" width="full" gap="8" horizontal-alignment="right" vertical-alignment="center">
                        <nldd-text-cell text={eenheid.eenheid_naam} width="fit-content" />
                        <nldd-container layout="row" gap="6" vertical-alignment="center">
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
                        </nldd-container>
                      </nldd-container>
                    </nldd-list-item>
                  ))}
                </nldd-list>
              )}

              {isEigenaar && (
                <nldd-container layout="row" gap="8" vertical-alignment="top">
                  <nldd-container width="fit-content" className="row-fill">
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
                  </nldd-container>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon="apartment-building"
                    onClick={() => {
                      if (addEenheidValue) handleAddEenheid(addEenheidValue);
                    }}
                    disabled={!addEenheidValue}
                  >
                    Toevoegen
                  </Button>
                </nldd-container>
              )}
            </nldd-container>

            {/* Stakeholders */}
            <nldd-container gap="8">
              <SectionHeading icon="person" text="Stakeholders" />
              <StakeholderTab
                scopeType="initiatief"
                scopeId={detail.id}
                readOnly={!canEdit}
              />
            </nldd-container>

            {/* Mattermost-kanalen */}
            <MattermostChannelsSection
              scope={{ type: 'initiatief', id: detail.id }}
            />

            {/* Updates (publication posts) */}
            <UpdatesSection initiatief={detail} canEdit={canEdit} />

            {/* Funnel-kolommen — eigenaar only */}
            {isEigenaar && (
              <nldd-container gap="8">
                <SectionHeading icon="gear" text="Funnel-kolommen" />
                <ColumnsManager initiatiefId={detail.id} />
              </nldd-container>
            )}

            {/* Settings — eigenaar only */}
            {isEigenaar && <SettingsSection initiatief={detail} />}
          </nldd-container>
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
    <nldd-container gap="8">
      <SectionHeading icon="gear" text="Instellingen" />

      <nldd-container gap="16">
        {/* Publieke pagina */}
        <nldd-card>
          <nldd-container gap="12" padding="16">
            <nldd-container layout="row" gap="6" vertical-alignment="center">
              <Icon name="globe" size="sm" />
              <nldd-text size="xs" weight="bold" color="secondary">
                Publieke pagina
              </nldd-text>
            </nldd-container>

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

            <nldd-container gap="6" style={initiatief.public_page_enabled || !initiatief.slug ? undefined : { opacity: 0.6 }}>
              <nldd-form-field label="Slug" supporting-label="publieke URL-segment">
                {initiatief.slug ? (
                  initiatief.public_page_enabled ? (
                    <nldd-link
                      href={`/c/${initiatief.slug}`}
                      target="_blank"
                      size="sm"
                      text={`/c/${initiatief.slug}`}
                      end-icon="external-link"
                    />
                  ) : (
                    <nldd-text size="sm">/c/{initiatief.slug}</nldd-text>
                  )
                ) : (
                  <nldd-container gap="6">
                    <nldd-text size="xs" color="secondary">
                      Nog geen slug ingesteld. Kies kleine letters, cijfers en
                      streepjes (bv. <code>regelrecht</code>).
                    </nldd-text>
                    <nldd-container layout="row" gap="8" vertical-alignment="top">
                      <nldd-text size="sm" color="secondary">/c/</nldd-text>
                      <nldd-container width="fit-content" className="row-fill">
                        <SlugDraftField
                          value={slugDraft}
                          onChange={(v) => {
                            setSlugDraft(v.toLowerCase());
                            setSlugError(null);
                          }}
                        />
                      </nldd-container>
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
                    </nldd-container>
                    {slugError && <nldd-text size="xs" color="critical">{slugError}</nldd-text>}
                  </nldd-container>
                )}
              </nldd-form-field>
            </nldd-container>
          </nldd-container>
        </nldd-card>

        {/* Funnel-afweging */}
        <nldd-card>
          <nldd-container gap="12" padding="16">
            <nldd-container layout="row" gap="6" vertical-alignment="center">
              <Icon name="person-badge-plus" size="sm" />
              <nldd-text size="xs" weight="bold" color="secondary">
                Funnel-afweging
              </nldd-text>
            </nldd-container>

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
              <nldd-container gap="8" padding-top="8">
                <nldd-text size="xs" color="secondary">
                  Optionele eigen labels voor de drie funnel-scores. Leeg laten
                  gebruikt de standaard.
                </nldd-text>
                <nldd-container layout="grid" column-count={1} sm-column-count={3} gap="8">
                  {(
                    [
                      ['score_strategisch_label', 'Strategisch belang'],
                      ['score_politiek_label', 'Politiek belang'],
                      ['score_positie_label', 'Positie / omgeving'],
                    ] as const
                  ).map(([key, fallback]) => (
                    <nldd-form-field key={key} label={fallback}>
                      <ScoreLabelField
                        value={scoreLabels[key]}
                        placeholder={fallback}
                        onCommit={(v) => {
                          const next = { ...scoreLabels, [key]: v };
                          setScoreLabels(next);
                          persistLabels(next);
                        }}
                      />
                    </nldd-form-field>
                  ))}
                </nldd-container>
              </nldd-container>
            )}
          </nldd-container>
        </nldd-card>
      </nldd-container>

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
    </nldd-container>
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
    <nldd-container layout="row" gap="12" horizontal-alignment="right" vertical-alignment="top">
      <nldd-container layout="row" gap="8" vertical-alignment="top">
        <Icon name={icon} size="sm" />
        <nldd-container gap="0" width="fit-content">
          <nldd-text size="sm" weight="medium">{label}</nldd-text>
          <nldd-text size="xs" color="secondary">{description}</nldd-text>
        </nldd-container>
      </nldd-container>
      <nldd-switch
        ref={ref}
        checked={orUndef(enabled)}
        {...(loading || disabled ? { disabled: true } : {})}
        accessible-label={label}
      />
    </nldd-container>
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
    <nldd-container gap="8">
      <nldd-container layout="row" width="full" gap="8" horizontal-alignment="right" vertical-alignment="center">
        <SectionHeading icon="megaphone" text={`Updates (${posts.length})`} />
        {canEdit && !composing && (
          <Button variant="secondary" size="sm" onClick={startCompose}>
            Nieuwe update
          </Button>
        )}
      </nldd-container>

      {composing && (
        <nldd-card>
          <nldd-container gap="8" padding="12">
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
            <nldd-container layout="row" gap="8" horizontal-alignment="right">
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
            </nldd-container>
          </nldd-container>
        </nldd-card>
      )}

      {concepts.length > 0 && (
        <nldd-container gap="4">
          <nldd-text size="xs" color="secondary">Concepten</nldd-text>
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
        </nldd-container>
      )}

      {published.length > 0 ? (
        <nldd-container gap="4">
          <nldd-text size="xs" color="secondary">Gepubliceerd</nldd-text>
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
        </nldd-container>
      ) : (
        concepts.length === 0 &&
        !composing && (
          <nldd-text size="sm" color="secondary">
            Nog geen updates. Klik op &quot;Nieuwe update&quot; om iets te publiceren.
          </nldd-text>
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
    </nldd-container>
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
      <nldd-container layout="row" width="full" gap="8" horizontal-alignment="right" vertical-alignment="top">
        <nldd-container gap="4" width="full">
          <nldd-container layout="row" gap="8" vertical-alignment="center">
            <nldd-text-cell text={post.titel} width="fit-content" />
            {isPublished ? (
              <Badge variant="green">Gepubliceerd</Badge>
            ) : (
              <Badge variant="gray">Concept</Badge>
            )}
          </nldd-container>
          {post.body && (
            <nldd-text size="sm" color="secondary">
              <RichTextDisplay content={post.body} />
            </nldd-text>
          )}
          {isPublished && post.published_at && (
            <nldd-text size="xs" color="secondary">
              {new Date(post.published_at).toLocaleString('nl-NL')}
              {post.published_by_naam && ` · ${post.published_by_naam}`}
            </nldd-text>
          )}
        </nldd-container>
        {canEdit && (
          <nldd-container layout="row" gap="4" vertical-alignment="center">
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
          </nldd-container>
        )}
      </nldd-container>
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
    <nldd-container gap="16">
      <nldd-form-field label="Naam">
        <NaamField value={form.naam || ''} onChange={(v) => onChange({ ...form, naam: v })} />
      </nldd-form-field>
      <RichTextFormField
        label="Beschrijving"
        value={form.beschrijving || ''}
        onChange={(value) => onChange({ ...form, beschrijving: value })}
        rows={4}
      />
      <nldd-form-field label="Kleur">
        <InitiatiefKleurPicker
          value={form.kleur}
          onChange={(kleur) => onChange({ ...form, kleur })}
        />
      </nldd-form-field>
    </nldd-container>
  );
}
