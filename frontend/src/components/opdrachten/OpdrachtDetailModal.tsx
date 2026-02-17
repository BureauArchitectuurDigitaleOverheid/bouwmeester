import { useState } from 'react';
import { Pencil, Trash2, Link as LinkIcon, ArrowRight } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { OpdrachtForm } from './OpdrachtForm';
import { useOpdracht, useDeleteOpdracht } from '@/hooks/useOpdrachten';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import {
  OPDRACHT_TYPE_LABELS,
  OPDRACHT_STATUS_LABELS,
  OPDRACHT_STATUS_COLORS,
  OPDRACHT_TYPE_COLORS,
  KOSTENSOORT_LABELS,
  NODE_TYPE_COLORS,
  OpdrachtType,
  OpdrachtStatus,
  Kostensoort,
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
  const deleteMutation = useDeleteOpdracht();
  const { openNodeDetail } = useNodeDetail();
  const [showEdit, setShowEdit] = useState(false);
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
          modal
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

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isLoading ? 'Laden...' : opdracht?.titel ?? 'Opdracht niet gevonden'}
      size="lg"
      zIndex={zIndex}
      footer={
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2">
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
          </div>
          <Button variant="secondary" onClick={onClose}>
            Sluiten
          </Button>
        </div>
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
                        onClick={() => openNodeDetail(opdracht.instrument!.id)}
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
                <div className="flex justify-between">
                  <dt className="text-text-secondary">Budget</dt>
                  <dd className="text-text font-medium tabular-nums">{formatCurrency(opdracht.budget)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-text-secondary">Gerealiseerd</dt>
                  <dd className="text-text font-medium tabular-nums">{formatCurrency(opdracht.gerealiseerd)}</dd>
                </div>
                {uitnutting !== null && (
                  <div className="flex justify-between">
                    <dt className="text-text-secondary">Uitnutting</dt>
                    <dd className="text-text font-medium">{uitnutting.toFixed(1)}%</dd>
                  </div>
                )}
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

              {uitnutting !== null && (
                <div className="mt-3">
                  <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-primary-500 transition-all"
                      style={{ width: `${Math.min(uitnutting, 100)}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Subsidie section */}
          {opdracht.type === 'subsidie' && (opdracht.subsidieregeling || opdracht.beschikking_nummer) && (
            <div className="border-t border-border pt-4">
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">Subsidie-gegevens</h4>
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
            </div>
          )}

          {/* Linked nodes */}
          {opdracht.node_koppelingen && opdracht.node_koppelingen.length > 0 && (
            <div className="border-t border-border pt-4">
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
                <LinkIcon className="h-3.5 w-3.5 inline mr-1 -mt-0.5" />
                Gekoppelde nodes ({opdracht.node_koppelingen.length})
              </h4>
              <div className="space-y-1">
                {opdracht.node_koppelingen.map((koppeling) => (
                  <button
                    key={koppeling.id}
                    onClick={() => openNodeDetail(koppeling.node_id)}
                    className="flex items-center gap-2 w-full p-1.5 rounded-lg hover:bg-gray-50 transition-colors text-left group"
                  >
                    {koppeling.node_type && (
                      <Badge
                        variant={NODE_TYPE_COLORS[koppeling.node_type as NodeType] ?? 'gray'}
                        dot
                      >
                        {koppeling.node_type}
                      </Badge>
                    )}
                    <span className="text-sm text-text truncate group-hover:text-primary-700 transition-colors">
                      {koppeling.node_title || koppeling.node_id}
                    </span>
                    {koppeling.relatie_type && (
                      <span className="text-xs text-text-secondary ml-auto shrink-0">
                        {koppeling.relatie_type}
                      </span>
                    )}
                    <ArrowRight className="h-3.5 w-3.5 text-gray-300 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
