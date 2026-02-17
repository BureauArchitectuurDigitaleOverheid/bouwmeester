import { useState } from 'react';
import { Pencil, Trash2, Link as LinkIcon, CheckSquare, Plus, ClipboardList } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { DetailSection } from '@/components/common/DetailSection';
import { RelatedItemsList } from '@/components/common/RelatedItemsList';
import { DetailModalFooter } from '@/components/common/DetailModalFooter';
import { OpdrachtForm } from './OpdrachtForm';
import { TaskCreateForm } from '@/components/tasks/TaskCreateForm';
import { useOpdracht, useDeleteOpdracht } from '@/hooks/useOpdrachten';
import { useTasksByOpdracht } from '@/hooks/useTasks';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useOpdrachtDetail } from '@/contexts/OpdrachtDetailContext';
import {
  OPDRACHT_TYPE_LABELS,
  OPDRACHT_STATUS_LABELS,
  OPDRACHT_STATUS_COLORS,
  OPDRACHT_TYPE_COLORS,
  KOSTENSOORT_LABELS,
  NODE_TYPE_COLORS,
  TASK_STATUS_LABELS,
  TASK_STATUS_COLORS,
  OpdrachtType,
  OpdrachtStatus,
  Kostensoort,
  TaskStatus,
  type NodeType,
} from '@/types';
import { formatCurrency } from '@/utils/format';

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
  const { openNodeDetail } = useNodeDetail();
  const { openTaskDetail } = useTaskDetail();
  const { opdrachtParentLabel } = useOpdrachtDetail();
  const [showEdit, setShowEdit] = useState(false);
  const [showTaskCreate, setShowTaskCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
  const uitnutting = budget > 0 ? (gerealiseerd / budget * 100) : null;

  const handleDelete = async () => {
    if (!opdrachtId) return;
    if (window.confirm('Weet je zeker dat je deze opdracht wilt verwijderen?')) {
      try {
        await deleteMutation.mutateAsync(opdrachtId);
        onClose();
      } catch {
        setError('Fout bij verwijderen van opdracht.');
      }
    }
  };

  const accentColor = opdracht ? OPDRACHT_TYPE_COLORS[opdracht.type as OpdrachtType] : undefined;

  return (
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
                onClick={handleDelete}
                disabled={!opdracht || deleteMutation.isPending}
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

          {/* Type + status badges */}
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={OPDRACHT_TYPE_COLORS[opdracht.type as OpdrachtType] || 'gray'}>
              {OPDRACHT_TYPE_LABELS[opdracht.type as OpdrachtType] || opdracht.type}
            </Badge>
            <Badge variant={OPDRACHT_STATUS_COLORS[opdracht.status as OpdrachtStatus] || 'gray'}>
              {OPDRACHT_STATUS_LABELS[opdracht.status as OpdrachtStatus] || opdracht.status}
            </Badge>
          </div>

          {/* Description */}
          {opdracht.beschrijving && (
            <p className="text-sm text-text-secondary">{opdracht.beschrijving}</p>
          )}

          {/* Financial hero */}
          {budget > 0 && (
            <div className="flex items-baseline gap-8">
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
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-text-secondary">Begrotingsjaar</dt>
                  <dd className="text-text font-medium">{opdracht.begrotingsjaar}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-text-secondary">Instrument</dt>
                  <dd>
                    {opdracht.instrument ? (
                      <button
                        onClick={() => openNodeDetail(opdracht.instrument!.id, opdracht.titel)}
                        className="text-primary-700 hover:text-primary-900 transition-colors font-medium"
                      >
                        {opdracht.instrument.title}
                      </button>
                    ) : '-'}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-text-secondary">Opdrachtnemer</dt>
                  <dd className="text-text">{opdracht.opdrachtnemer?.afkorting || opdracht.opdrachtnemer?.naam || '-'}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-text-secondary">Opdrachtgever</dt>
                  <dd className="text-text">{opdracht.opdrachtgever?.naam || '-'}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-text-secondary">Verantwoordelijke</dt>
                  <dd className="text-text">{opdracht.verantwoordelijke?.naam || '-'}</dd>
                </div>
                {opdracht.referentie && (
                  <div className="flex justify-between">
                    <dt className="text-text-secondary">Referentie</dt>
                    <dd className="text-text">{opdracht.referentie}</dd>
                  </div>
                )}
                {opdracht.kostensoort && (
                  <div className="flex justify-between">
                    <dt className="text-text-secondary">Kostensoort</dt>
                    <dd className="text-text">{KOSTENSOORT_LABELS[opdracht.kostensoort as Kostensoort] || opdracht.kostensoort}</dd>
                  </div>
                )}
                {opdracht.startdatum && (
                  <div className="flex justify-between">
                    <dt className="text-text-secondary">Periode</dt>
                    <dd className="text-text">{opdracht.startdatum} — {opdracht.einddatum || '...'}</dd>
                  </div>
                )}
              </dl>
            </div>

            <div className="space-y-3">
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Financieel</h4>
              <dl className="space-y-2 text-sm">
                {opdracht.volgend_jaar_benodigd != null && (
                  <div className="flex justify-between">
                    <dt className="text-text-secondary">Volgend jaar benodigd</dt>
                    <dd className="text-text tabular-nums">{formatCurrency(opdracht.volgend_jaar_benodigd)}</dd>
                  </div>
                )}
                {opdracht.volgend_jaar_aangevraagd != null && (
                  <div className="flex justify-between">
                    <dt className="text-text-secondary">Volgend jaar aangevraagd</dt>
                    <dd className="text-text tabular-nums">{formatCurrency(opdracht.volgend_jaar_aangevraagd)}</dd>
                  </div>
                )}
              </dl>
            </div>
          </div>

          {/* Subsidie section */}
          {opdracht.type === 'subsidie' && (opdracht.subsidieregeling || opdracht.beschikking_nummer) && (
            <DetailSection title="Subsidie-gegevens" separated>
              <dl className="space-y-2 text-sm">
                {opdracht.subsidieregeling && (
                  <div className="flex justify-between">
                    <dt className="text-text-secondary">Subsidieregeling</dt>
                    <dd className="text-text">{opdracht.subsidieregeling}</dd>
                  </div>
                )}
                {opdracht.beschikking_nummer && (
                  <div className="flex justify-between">
                    <dt className="text-text-secondary">Beschikking nr.</dt>
                    <dd className="text-text">{opdracht.beschikking_nummer}</dd>
                  </div>
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

          {/* Tasks */}
          <DetailSection
            title="Taken"
            icon={<CheckSquare className="h-3.5 w-3.5" />}
            count={tasks.length}
            separated
            action={
              <button
                onClick={() => setShowTaskCreate(true)}
                className="flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-800 transition-colors"
              >
                <Plus className="h-3.5 w-3.5" />
                Taak
              </button>
            }
          >
            <RelatedItemsList
              items={tasks.map((task) => ({
                id: task.id,
                label: task.title,
                badge: {
                  text: TASK_STATUS_LABELS[task.status as TaskStatus] ?? task.status,
                  variant: TASK_STATUS_COLORS[task.status as TaskStatus] ?? 'gray',
                },
                secondaryText: task.assignee?.naam,
                onClick: () => openTaskDetail(task.id, opdracht.titel),
              }))}
              maxVisible={5}
              emptyLabel="Geen taken gekoppeld"
            />
          </DetailSection>
        </div>
      )}

      <TaskCreateForm
        open={showTaskCreate}
        onClose={() => setShowTaskCreate(false)}
        nodeId={opdracht?.instrument_id}
        opdrachtId={opdrachtId ?? undefined}
      />
    </Modal>
  );
}
