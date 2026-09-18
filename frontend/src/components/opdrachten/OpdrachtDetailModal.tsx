import { useRef, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Modal } from '@/components/common/Modal';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { DetailSection } from '@/components/common/DetailSection';
import { DetailMetadataGrid } from '@/components/common/DetailMetadataGrid';
import { RelatedItemsList } from '@/components/common/RelatedItemsList';
import { DetailModalFooter } from '@/components/common/DetailModalFooter';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { Icon } from '@/components/nldd/Icon';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { useNlddEvent } from '@/components/nldd/events';

/** An `nldd-link` with its click bridged to React, for an in-page navigation action inside plain text. */
function ActionLink({ text, onClick }: { text: string; onClick: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick);
  return <nldd-link ref={ref} text={text} />;
}

/** `SyncStatus` -> the design system's five semantic roles. */
const SYNC_STATUS_TAG_COLOR: Record<SyncStatus, 'success' | 'warning' | 'accent' | 'critical'> = {
  synced: 'success',
  pending_push: 'warning',
  pending_pull: 'accent',
  conflict: 'critical',
  error: 'critical',
};

/** Small "matched by AI" indicator, shown next to a member/eenheid name. */
function AiMatchedTag({ reason, confidence }: { reason?: string | null; confidence?: number | null }) {
  return (
    <nldd-tag
      text="AI"
      icon="sparkles"
      color="warning"
      size="sm"
      title={reason ? `${reason} (${Math.round((confidence ?? 0) * 100)}%)` : 'Door AI gematcht'}
    />
  );
}
import { FccDataSection } from './FccDataSection';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { Select } from '@/components/common/Select';
import { OpdrachtForm } from './OpdrachtForm';
import { TaskCreateForm } from '@/components/tasks/TaskCreateForm';
import {
  useOpdracht, useDeleteOpdracht,
  useAddOpdrachtMember, useRemoveOpdrachtMember, useUpdateOpdrachtMemberRole,
  useAddOpdrachtEenheid, useRemoveOpdrachtEenheid, useUpdateOpdrachtEenheidRol,
  useMatchOpdrachtContacts,
} from '@/hooks/useOpdrachten';
import { useTasksByOpdracht } from '@/hooks/useTasks';
import { usePeople } from '@/hooks/usePeople';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useOpdrachtDetail } from '@/contexts/OpdrachtDetailContext';
import {
  OPDRACHT_TYPE_LABELS,
  OPDRACHT_STATUS_LABELS,
  OPDRACHT_STATUS_COLORS,
  OPDRACHT_TYPE_COLORS,
  OPDRACHT_CONTACT_ROL_LABELS,
  KOSTENSOORT_LABELS,
  NODE_TYPE_COLORS,
  SYNC_STATUS_LABELS,
  OpdrachtType,
  OpdrachtStatus,
  Kostensoort,
  TaskStatus,
  type NodeType,
  type SyncStatus,
} from '@/types';
import { formatCurrency, calculateUtilization } from '@/utils/format';

interface OpdrachtDetailModalProps {
  opdrachtId: string | null;
  open: boolean;
  onClose: () => void;
  zIndex?: number;
}

export function OpdrachtDetailModal({ opdrachtId, open, onClose, zIndex }: OpdrachtDetailModalProps) {
  const { data: opdracht, isLoading } = useOpdracht(opdrachtId ?? undefined);
  const { data: tasks = [] } = useTasksByOpdracht(opdrachtId);
  const deleteMutation = useDeleteOpdracht();
  const navigate = useNavigate();
  const { openNodeDetail } = useNodeDetail();
  const { openTaskDetail } = useTaskDetail();
  const { opdrachtParentLabel } = useOpdrachtDetail();
  const [showEdit, setShowEdit] = useState(false);
  const [showTaskCreate, setShowTaskCreate] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addMemberValue, setAddMemberValue] = useState('');
  const [addEenheidValue, setAddEenheidValue] = useState('');

  // Member/eenheid hooks
  const { data: allPeople = [] } = usePeople();
  const { data: allEenheden = [] } = useOrganisatieFlat();
  const addMemberMutation = useAddOpdrachtMember();
  const removeMemberMutation = useRemoveOpdrachtMember();
  const updateMemberRoleMutation = useUpdateOpdrachtMemberRole();
  const addEenheidMutation = useAddOpdrachtEenheid();
  const removeEenheidMutation = useRemoveOpdrachtEenheid();
  const updateEenheidRolMutation = useUpdateOpdrachtEenheidRol();
  const matchContactsMutation = useMatchOpdrachtContacts();

  const members = opdracht?.members ?? [];
  const eenheden = opdracht?.eenheden ?? [];

  const availablePeopleOptions = useMemo(() => {
    const memberIds = new Set(members.map((m) => m.person_id));
    return allPeople
      .filter((p) => !memberIds.has(p.id) && !p.is_agent)
      .map((p) => ({ value: p.id, label: p.naam }));
  }, [allPeople, members]);

  const availableEenheidOptions = useMemo(() => {
    const linkedIds = new Set(eenheden.map((e) => e.eenheid_id));
    return allEenheden
      .filter((e) => !linkedIds.has(e.id))
      .map((e) => ({ value: e.id, label: e.naam }));
  }, [allEenheden, eenheden]);

  if (!open) return null;

  if (showEdit && opdracht) {
    return (
      <Modal
        open={open}
        onClose={() => { setShowEdit(false); onClose(); }}
        title="Opdracht bewerken"
        size="lg"
        zIndex={zIndex}
      >
        <OpdrachtForm
          opdracht={opdracht}
          onClose={() => setShowEdit(false)}
          onSuccess={() => setShowEdit(false)}
        />
      </Modal>
    );
  }

  const budget = Number(opdracht?.budget) || 0;
  const gerealiseerd = Number(opdracht?.gerealiseerd) || 0;
  const uitnutting = calculateUtilization(opdracht?.budget, opdracht?.gerealiseerd);

  const handleDelete = async () => {
    if (!opdrachtId) return;
    try {
      await deleteMutation.mutateAsync(opdrachtId);
      setShowDeleteConfirm(false);
      onClose();
    } catch {
      setError('Fout bij verwijderen van opdracht.');
    }
  };

  const accentColor = opdracht ? OPDRACHT_TYPE_COLORS[opdracht.type as OpdrachtType] : undefined;

  const handleAddMember = async (personId: string) => {
    if (!opdrachtId || !personId) return;
    await addMemberMutation.mutateAsync({ opdrachtId, personId });
    setAddMemberValue('');
  };

  const handleRemoveMember = async (personId: string) => {
    if (!opdrachtId) return;
    await removeMemberMutation.mutateAsync({ opdrachtId, personId });
  };

  const handleUpdateMemberRole = async (personId: string, rol: string) => {
    if (!opdrachtId) return;
    await updateMemberRoleMutation.mutateAsync({ opdrachtId, personId, rol });
  };

  const handleAddEenheid = async (eenheidId: string) => {
    if (!opdrachtId || !eenheidId) return;
    await addEenheidMutation.mutateAsync({ opdrachtId, eenheidId });
    setAddEenheidValue('');
  };

  const handleRemoveEenheid = async (eenheidId: string) => {
    if (!opdrachtId) return;
    await removeEenheidMutation.mutateAsync({ opdrachtId, eenheidId });
  };

  const handleUpdateEenheidRol = async (eenheidId: string, rol: string) => {
    if (!opdrachtId) return;
    await updateEenheidRolMutation.mutateAsync({ opdrachtId, eenheidId, rol });
  };

  const handleMatchContacts = async () => {
    if (!opdrachtId) return;
    await matchContactsMutation.mutateAsync(opdrachtId);
  };

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={isLoading ? 'Laden...' : opdracht?.titel ?? 'Opdracht niet gevonden'}
        size="lg"
        zIndex={zIndex}
        accentColor={accentColor}
        headerIcon={<Icon name="clipboard-bullet-list" size="lg" />}
        entityLabel={opdracht ? (OPDRACHT_TYPE_LABELS[opdracht.type as OpdrachtType] || opdracht.type) : undefined}
        backLabel={opdrachtParentLabel ?? undefined}
        onBack={opdrachtParentLabel ? onClose : undefined}
        footer={
          <DetailModalFooter
            onClose={onClose}
            actions={
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  icon="pencil"
                  onClick={() => setShowEdit(true)}
                  disabled={!opdracht}
                >
                  Bewerken
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  icon="trash"
                  onClick={() => setShowDeleteConfirm(true)}
                  disabled={!opdracht}
                  className="text-red-600 hover:text-red-700"
                >
                  Verwijderen
                </Button>
              </>
            }
          />
        }
      >
        {isLoading ? (
          <nldd-activity-indicator size="24" text="Laden..." show-text className="mx-auto my-8 block" />
        ) : !opdracht ? (
          <nldd-inline-dialog icon="question-mark-circle" text="Opdracht niet gevonden." />
        ) : (
          <div className="space-y-5">
            {/* Error feedback */}
            {error && <nldd-banner variant="critical" size="sm" text={error} />}

            {/* Type + status + sync badges */}
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant={OPDRACHT_TYPE_COLORS[opdracht.type as OpdrachtType] || 'gray'}>
                {OPDRACHT_TYPE_LABELS[opdracht.type as OpdrachtType] || opdracht.type}
              </Badge>
              <Badge variant={OPDRACHT_STATUS_COLORS[opdracht.status as OpdrachtStatus] || 'gray'}>
                {OPDRACHT_STATUS_LABELS[opdracht.status as OpdrachtStatus] || opdracht.status}
              </Badge>
              {opdracht.sync_status && (
                <nldd-tag
                  text={`FCC: ${SYNC_STATUS_LABELS[opdracht.sync_status as SyncStatus] || opdracht.sync_status}`}
                  color={SYNC_STATUS_TAG_COLOR[opdracht.sync_status as SyncStatus] ?? 'neutral'}
                  size="sm"
                />
              )}
            </div>

            {/* Description */}
            {opdracht.beschrijving && (
              <DetailSection title="Beschrijving">
                <RichTextDisplay content={opdracht.beschrijving} />
              </DetailSection>
            )}

            {/* Financial hero */}
            {budget > 0 && (
              <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
                <div>
                  <nldd-text size="xs" color="secondary" className="uppercase tracking-wider">Budget</nldd-text>
                  <p className="text-xl font-semibold tabular-nums">{formatCurrency(opdracht.budget)}</p>
                </div>
                {uitnutting !== null && (
                  <div>
                    <nldd-text size="xs" color="secondary" className="uppercase tracking-wider">Uitnutting</nldd-text>
                    <p className="text-xl font-semibold tabular-nums">{uitnutting.toFixed(1)}%</p>
                  </div>
                )}
                {gerealiseerd > 0 && (
                  <div>
                    <nldd-text size="xs" color="secondary" className="uppercase tracking-wider">Gerealiseerd</nldd-text>
                    <p className="text-xl font-semibold tabular-nums">{formatCurrency(opdracht.gerealiseerd)}</p>
                  </div>
                )}
              </div>
            )}
            {uitnutting !== null && (
              <nldd-progress-bar value={Math.min(uitnutting, 100)} max={100} size="sm" value-display="none" />
            )}

            {/* Details + Financieel grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div className="space-y-3">
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Details</h4>
                <DetailMetadataGrid
                  items={[
                    { label: 'Begrotingsjaar', value: opdracht.begrotingsjaar },
                    {
                      label: 'Instrument',
                      value: opdracht.instrument ? (
                        <ActionLink
                          text={opdracht.instrument.title}
                          onClick={() => openNodeDetail(opdracht.instrument!.id, opdracht.titel)}
                        />
                      ) : undefined,
                    },
                    {
                      label: 'Opdrachtnemer',
                      value: opdracht.opdrachtnemer ? (
                        <ActionLink
                          text={opdracht.opdrachtnemer.afkorting || opdracht.opdrachtnemer.naam}
                          onClick={() => { onClose(); navigate('/externe-organisaties'); }}
                        />
                      ) : undefined,
                    },
                    {
                      label: 'Opdrachtgever',
                      value: opdracht.opdrachtgever ? (
                        <ActionLink
                          text={opdracht.opdrachtgever.naam}
                          onClick={() => { onClose(); navigate('/organisatie'); }}
                        />
                      ) : undefined,
                    },
                    {
                      label: 'Verantwoordelijke',
                      value: opdracht.verantwoordelijke ? (
                        <ActionLink
                          text={opdracht.verantwoordelijke.naam}
                          onClick={() => { onClose(); navigate('/people'); }}
                        />
                      ) : undefined,
                    },
                    { label: 'Referentie', value: opdracht.referentie },
                    {
                      label: 'Kostensoort',
                      value: opdracht.kostensoort
                        ? KOSTENSOORT_LABELS[opdracht.kostensoort as Kostensoort] || opdracht.kostensoort
                        : undefined,
                    },
                    {
                      label: 'Periode',
                      value: opdracht.startdatum
                        ? `${opdracht.startdatum} — ${opdracht.einddatum || '...'}`
                        : undefined,
                    },
                  ]}
                />
              </div>

              <div className="space-y-3">
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Financieel</h4>
                <DetailMetadataGrid
                  items={[
                    {
                      label: 'Volgend jaar benodigd',
                      value: opdracht.volgend_jaar_benodigd != null ? formatCurrency(opdracht.volgend_jaar_benodigd) : undefined,
                    },
                    {
                      label: 'Volgend jaar aangevraagd',
                      value: opdracht.volgend_jaar_aangevraagd != null ? formatCurrency(opdracht.volgend_jaar_aangevraagd) : undefined,
                    },
                  ]}
                />
              </div>
            </div>

            {/* FCC data section */}
            {opdracht.fcc_id && opdracht.fcc_raw_data && (
              <FccDataSection
                data={opdracht.fcc_raw_data}
                funnelfase={opdracht.fcc_funnelfase}
                afdeling={opdracht.fcc_afdeling}
                portfolio={opdracht.fcc_portfolio}
                labels={opdracht.fcc_labels}
              />
            )}

            {/* Subsidie section */}
            {opdracht.type === 'subsidie' && (opdracht.subsidieregeling || opdracht.beschikking_nummer) && (
              <DetailSection title="Subsidie-gegevens" separated>
                <DetailMetadataGrid
                  items={[
                    { label: 'Subsidieregeling', value: opdracht.subsidieregeling },
                    { label: 'Beschikking nr.', value: opdracht.beschikking_nummer },
                  ]}
                />
              </DetailSection>
            )}

            {/* Linked nodes */}
            {opdracht.node_koppelingen && opdracht.node_koppelingen.length > 0 && (
              <DetailSection
                title="Gekoppelde nodes"
                icon={<Icon name="link" size="sm" />}
                count={opdracht.node_koppelingen.length}
                separated
              >
                <RelatedItemsList
                  items={opdracht.node_koppelingen.map((koppeling) => ({
                    id: koppeling.id,
                    label: koppeling.node_title || koppeling.node_id,
                    badge: koppeling.node_type ? {
                      text: koppeling.node_type,
                      variant: NODE_TYPE_COLORS[koppeling.node_type as NodeType] ?? 'gray',
                      dot: true,
                    } : undefined,
                    secondaryText: koppeling.relatie_type ?? undefined,
                    onClick: () => openNodeDetail(koppeling.node_id, opdracht.titel),
                  }))}
                  maxVisible={5}
                  emptyLabel="Geen gekoppelde nodes"
                />
              </DetailSection>
            )}

            {/* Contactpersonen */}
            <DetailSection
              title="Contactpersonen"
              icon={<Icon name="users" size="sm" />}
              count={members.length}
              separated
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  icon="sparkles"
                  onClick={handleMatchContacts}
                  disabled={matchContactsMutation.isPending}
                >
                  {matchContactsMutation.isPending ? 'Matchen...' : 'Matchen'}
                </Button>
              }
            >
              {members.length > 0 && (
                <nldd-list variant="box-tinted" dividers="always" className="mb-3">
                  {members.map((member) => (
                    <nldd-list-item key={member.person_id}>
                      <nldd-text-cell>
                        <div className="flex items-center gap-2 min-w-0">
                          <ActionLink
                            text={member.person_naam}
                            onClick={() => { onClose(); navigate(`/people?highlight=${member.person_id}`); }}
                          />
                          {member.source === 'ai' && (
                            <AiMatchedTag reason={member.ai_reason} confidence={member.ai_confidence} />
                          )}
                        </div>
                      </nldd-text-cell>
                      <div className="w-36">
                        <Select
                          value={member.rol}
                          onChange={(e) => handleUpdateMemberRole(member.person_id, e.target.value)}
                          options={Object.entries(OPDRACHT_CONTACT_ROL_LABELS).map(([value, label]) => ({ value, label }))}
                        />
                      </div>
                      <NlddIconButton
                        icon="trash"
                        variant="neutral-transparent"
                        size="sm"
                        accessibleLabel="Verwijderen"
                        onClick={() => handleRemoveMember(member.person_id)}
                      />
                    </nldd-list-item>
                  ))}
                </nldd-list>
              )}

              <div className="flex items-start gap-2">
                <div className="flex-1">
                  <CreatableSelect
                    value={addMemberValue}
                    onChange={(val) => {
                      setAddMemberValue(val);
                      if (val) handleAddMember(val);
                    }}
                    options={availablePeopleOptions}
                    placeholder="Contactpersoon toevoegen..."
                    emptyMessage="Geen personen gevonden"
                  />
                </div>
              </div>
            </DetailSection>

            {/* Organisatie-eenheden */}
            <DetailSection
              title="Organisatie-eenheden"
              icon={<Icon name="apartment-building" size="sm" />}
              count={eenheden.length}
              separated
            >
              {eenheden.length > 0 && (
                <nldd-list variant="box-tinted" dividers="always" className="mb-3">
                  {eenheden.map((eenheid) => (
                    <nldd-list-item key={eenheid.eenheid_id}>
                      <nldd-text-cell>
                        <div className="flex items-center gap-2 min-w-0">
                          <ActionLink
                            text={eenheid.eenheid_naam}
                            onClick={() => { onClose(); navigate(`/organisatie?highlight=${eenheid.eenheid_id}`); }}
                          />
                          {eenheid.source === 'ai' && (
                            <AiMatchedTag reason={eenheid.ai_reason} confidence={eenheid.ai_confidence} />
                          )}
                        </div>
                      </nldd-text-cell>
                      <div className="w-36">
                        <Select
                          value={eenheid.rol}
                          onChange={(e) => handleUpdateEenheidRol(eenheid.eenheid_id, e.target.value)}
                          options={Object.entries(OPDRACHT_CONTACT_ROL_LABELS).map(([value, label]) => ({ value, label }))}
                        />
                      </div>
                      <NlddIconButton
                        icon="trash"
                        variant="neutral-transparent"
                        size="sm"
                        accessibleLabel="Verwijderen"
                        onClick={() => handleRemoveEenheid(eenheid.eenheid_id)}
                      />
                    </nldd-list-item>
                  ))}
                </nldd-list>
              )}

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
              </div>
            </DetailSection>

            {/* Tasks */}
            <DetailSection
              title="Taken"
              icon={<Icon name="check-list" size="sm" />}
              count={tasks.length}
              separated
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  icon="plus"
                  onClick={() => setShowTaskCreate(true)}
                >
                  Taak
                </Button>
              }
            >
              <RelatedItemsList
                items={tasks.map((task) => ({
                  id: task.id,
                  label: task.title,
                  icon: task.status === TaskStatus.DONE
                    ? <Icon name="check-mark-circle" size="md" className="text-emerald-500 shrink-0" />
                    : task.status === TaskStatus.IN_PROGRESS
                      ? <Icon name="clock" size="md" className="text-blue-500 shrink-0" />
                      : <Icon name="circle" size="md" className="text-gray-300 shrink-0" />,
                  secondaryText: task.assignee?.naam,
                  onClick: () => openTaskDetail(task.id, opdracht.titel),
                }))}
                maxVisible={5}
                emptyLabel="Geen taken gekoppeld"
              />
            </DetailSection>
          </div>
        )}
      </Modal>

      <TaskCreateForm
        open={showTaskCreate}
        onClose={() => setShowTaskCreate(false)}
        nodeId={opdracht?.instrument_id ?? undefined}
        opdrachtId={opdrachtId ?? undefined}
      />

      <ConfirmDialog
        open={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDelete}
        title="Opdracht verwijderen"
        confirmLabel="Verwijderen"
        variant="danger"
        loading={deleteMutation.isPending}
      >
        <p>Weet je zeker dat je <strong>{opdracht?.titel}</strong> wilt verwijderen?</p>
        {tasks.length > 0 && (
          <p className="mt-2">{tasks.length} gekoppelde taak/taken worden ook verwijderd.</p>
        )}
      </ConfirmDialog>
    </>
  );
}
