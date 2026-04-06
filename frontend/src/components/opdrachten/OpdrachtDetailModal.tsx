import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Pencil, Trash2, Link as LinkIcon, CheckSquare, Plus, ClipboardList, CheckCircle2, Circle, Clock, Users, Building2, X, Sparkles } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { DetailSection } from '@/components/common/DetailSection';
import { RelatedItemsList } from '@/components/common/RelatedItemsList';
import { DetailModalFooter } from '@/components/common/DetailModalFooter';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { FccDataSection } from './FccDataSection';
import { CreatableSelect } from '@/components/common/CreatableSelect';
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
  SYNC_STATUS_COLORS,
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
        headerIcon={<ClipboardList className="h-5 w-5" />}
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
                  icon={<Pencil className="h-4 w-4" />}
                  onClick={() => setShowEdit(true)}
                  disabled={!opdracht}
                >
                  Bewerken
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<Trash2 className="h-4 w-4" />}
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
          <div className="flex items-center justify-center py-8 text-text-secondary text-sm">
            Laden...
          </div>
        ) : !opdracht ? (
          <div className="flex items-center justify-center py-8 text-text-secondary text-sm">
            Opdracht niet gevonden.
          </div>
        ) : (
          <div className="space-y-5">
            {/* Error feedback */}
            {error && (
              <div className="p-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg">
                {error}
              </div>
            )}

            {/* Type + status + sync badges */}
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant={OPDRACHT_TYPE_COLORS[opdracht.type as OpdrachtType] || 'gray'}>
                {OPDRACHT_TYPE_LABELS[opdracht.type as OpdrachtType] || opdracht.type}
              </Badge>
              <Badge variant={OPDRACHT_STATUS_COLORS[opdracht.status as OpdrachtStatus] || 'gray'}>
                {OPDRACHT_STATUS_LABELS[opdracht.status as OpdrachtStatus] || opdracht.status}
              </Badge>
              {opdracht.sync_status && (
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${SYNC_STATUS_COLORS[opdracht.sync_status as SyncStatus] || 'bg-gray-100 text-gray-800'}`}>
                  FCC: {SYNC_STATUS_LABELS[opdracht.sync_status as SyncStatus] || opdracht.sync_status}
                </span>
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
                  <span className="text-xs text-text-secondary uppercase tracking-wider">Budget</span>
                  <p className="text-xl font-semibold tabular-nums">{formatCurrency(opdracht.budget)}</p>
                </div>
                {uitnutting !== null && (
                  <div>
                    <span className="text-xs text-text-secondary uppercase tracking-wider">Uitnutting</span>
                    <p className="text-xl font-semibold tabular-nums">{uitnutting.toFixed(1)}%</p>
                  </div>
                )}
                {gerealiseerd > 0 && (
                  <div>
                    <span className="text-xs text-text-secondary uppercase tracking-wider">Gerealiseerd</span>
                    <p className="text-xl font-semibold tabular-nums">{formatCurrency(opdracht.gerealiseerd)}</p>
                  </div>
                )}
              </div>
            )}
            {uitnutting !== null && (
              <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary-500 transition-all"
                  style={{ width: `${Math.min(uitnutting, 100)}%` }}
                />
              </div>
            )}

            {/* Details + Financieel grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <div className="space-y-3">
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Details</h4>
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                  <dt className="text-text-secondary">Begrotingsjaar</dt>
                  <dd className="text-text font-medium">{opdracht.begrotingsjaar}</dd>
                  <dt className="text-text-secondary">Instrument</dt>
                  <dd className="truncate">
                    {opdracht.instrument ? (
                      <button
                        onClick={() => openNodeDetail(opdracht.instrument!.id, opdracht.titel)}
                        className="text-primary-600 hover:text-primary-800 hover:underline transition-colors font-medium truncate max-w-full text-left"
                        title={opdracht.instrument.title}
                      >
                        {opdracht.instrument.title}
                      </button>
                    ) : '-'}
                  </dd>
                  <dt className="text-text-secondary">Opdrachtnemer</dt>
                  <dd>
                    {opdracht.opdrachtnemer ? (
                      <button
                        onClick={() => { onClose(); navigate(`/externe-organisaties`); }}
                        className="text-primary-600 hover:text-primary-800 hover:underline transition-colors font-medium"
                      >
                        {opdracht.opdrachtnemer.afkorting || opdracht.opdrachtnemer.naam}
                      </button>
                    ) : '-'}
                  </dd>
                  <dt className="text-text-secondary">Opdrachtgever</dt>
                  <dd>
                    {opdracht.opdrachtgever ? (
                      <button
                        onClick={() => { onClose(); navigate(`/organisatie`); }}
                        className="text-primary-600 hover:text-primary-800 hover:underline transition-colors font-medium"
                      >
                        {opdracht.opdrachtgever.naam}
                      </button>
                    ) : '-'}
                  </dd>
                  <dt className="text-text-secondary">Verantwoordelijke</dt>
                  <dd>
                    {opdracht.verantwoordelijke ? (
                      <button
                        onClick={() => { onClose(); navigate(`/people`); }}
                        className="text-primary-600 hover:text-primary-800 hover:underline transition-colors font-medium"
                      >
                        {opdracht.verantwoordelijke.naam}
                      </button>
                    ) : '-'}
                  </dd>
                  {opdracht.referentie && (
                    <>
                      <dt className="text-text-secondary">Referentie</dt>
                      <dd className="text-text">{opdracht.referentie}</dd>
                    </>
                  )}
                  {opdracht.kostensoort && (
                    <>
                      <dt className="text-text-secondary">Kostensoort</dt>
                      <dd className="text-text">{KOSTENSOORT_LABELS[opdracht.kostensoort as Kostensoort] || opdracht.kostensoort}</dd>
                    </>
                  )}
                  {opdracht.startdatum && (
                    <>
                      <dt className="text-text-secondary">Periode</dt>
                      <dd className="text-text">{opdracht.startdatum} — {opdracht.einddatum || '...'}</dd>
                    </>
                  )}
                </dl>
              </div>

              <div className="space-y-3">
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Financieel</h4>
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                  {opdracht.volgend_jaar_benodigd != null && (
                    <>
                      <dt className="text-text-secondary">Volgend jaar benodigd</dt>
                      <dd className="text-text tabular-nums">{formatCurrency(opdracht.volgend_jaar_benodigd)}</dd>
                    </>
                  )}
                  {opdracht.volgend_jaar_aangevraagd != null && (
                    <>
                      <dt className="text-text-secondary">Volgend jaar aangevraagd</dt>
                      <dd className="text-text tabular-nums">{formatCurrency(opdracht.volgend_jaar_aangevraagd)}</dd>
                    </>
                  )}
                </dl>
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
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                  {opdracht.subsidieregeling && (
                    <>
                      <dt className="text-text-secondary">Subsidieregeling</dt>
                      <dd className="text-text">{opdracht.subsidieregeling}</dd>
                    </>
                  )}
                  {opdracht.beschikking_nummer && (
                    <>
                      <dt className="text-text-secondary">Beschikking nr.</dt>
                      <dd className="text-text">{opdracht.beschikking_nummer}</dd>
                    </>
                  )}
                </dl>
              </DetailSection>
            )}

            {/* Linked nodes */}
            {opdracht.node_koppelingen && opdracht.node_koppelingen.length > 0 && (
              <DetailSection
                title="Gekoppelde nodes"
                icon={<LinkIcon className="h-3.5 w-3.5" />}
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
              icon={<Users className="h-3.5 w-3.5" />}
              count={members.length}
              separated
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Sparkles className="h-3.5 w-3.5" />}
                  onClick={handleMatchContacts}
                  disabled={matchContactsMutation.isPending}
                >
                  {matchContactsMutation.isPending ? 'Matchen...' : 'Matchen'}
                </Button>
              }
            >
              {members.length > 0 && (
                <ul className="divide-y divide-border rounded-xl border border-border mb-3">
                  {members.map((member) => (
                    <li
                      key={member.person_id}
                      className="flex items-center justify-between px-3 py-2"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <button
                          onClick={() => { onClose(); navigate(`/people?highlight=${member.person_id}`); }}
                          className="text-sm text-primary-600 hover:text-primary-800 hover:underline transition-colors font-medium truncate"
                        >
                          {member.person_naam}
                        </button>
                        {member.source === 'ai' && (
                          <span
                            className="inline-flex items-center gap-0.5 text-[10px] font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded px-1 py-0.5"
                            title={member.ai_reason ? `${member.ai_reason} (${Math.round((member.ai_confidence ?? 0) * 100)}%)` : 'Door AI gematcht'}
                          >
                            <Sparkles className="h-2.5 w-2.5" />
                            AI
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <select
                          value={member.rol}
                          onChange={(e) => handleUpdateMemberRole(member.person_id, e.target.value)}
                          className="text-xs border border-border rounded px-1.5 py-0.5 bg-white"
                        >
                          {Object.entries(OPDRACHT_CONTACT_ROL_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                          ))}
                        </select>
                        <button
                          onClick={() => handleRemoveMember(member.person_id)}
                          className="p-1 rounded hover:bg-gray-100 text-text-secondary hover:text-red-500 transition-colors"
                          title="Verwijderen"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
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
              icon={<Building2 className="h-3.5 w-3.5" />}
              count={eenheden.length}
              separated
            >
              {eenheden.length > 0 && (
                <ul className="divide-y divide-border rounded-xl border border-border mb-3">
                  {eenheden.map((eenheid) => (
                    <li
                      key={eenheid.eenheid_id}
                      className="flex items-center justify-between px-3 py-2"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <button
                          onClick={() => { onClose(); navigate(`/organisatie?highlight=${eenheid.eenheid_id}`); }}
                          className="text-sm text-primary-600 hover:text-primary-800 hover:underline transition-colors font-medium truncate"
                        >
                          {eenheid.eenheid_naam}
                        </button>
                        {eenheid.source === 'ai' && (
                          <span
                            className="inline-flex items-center gap-0.5 text-[10px] font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded px-1 py-0.5"
                            title={eenheid.ai_reason ? `${eenheid.ai_reason} (${Math.round((eenheid.ai_confidence ?? 0) * 100)}%)` : 'Door AI gematcht'}
                          >
                            <Sparkles className="h-2.5 w-2.5" />
                            AI
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <select
                          value={eenheid.rol}
                          onChange={(e) => handleUpdateEenheidRol(eenheid.eenheid_id, e.target.value)}
                          className="text-xs border border-border rounded px-1.5 py-0.5 bg-white"
                        >
                          {Object.entries(OPDRACHT_CONTACT_ROL_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                          ))}
                        </select>
                        <button
                          onClick={() => handleRemoveEenheid(eenheid.eenheid_id)}
                          className="p-1 rounded hover:bg-gray-100 text-text-secondary hover:text-red-500 transition-colors"
                          title="Verwijderen"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
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
              icon={<CheckSquare className="h-3.5 w-3.5" />}
              count={tasks.length}
              separated
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Plus className="h-3.5 w-3.5" />}
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
                    ? <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    : task.status === TaskStatus.IN_PROGRESS
                      ? <Clock className="h-4 w-4 text-blue-500 shrink-0" />
                      : <Circle className="h-4 w-4 text-gray-300 shrink-0" />,
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
