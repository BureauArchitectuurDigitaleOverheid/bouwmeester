import { useState } from 'react';
import { ArrowLeft, Edit2, Trash2 } from 'lucide-react';
import { useOpdracht, useDeleteOpdracht } from '@/hooks/useOpdrachten';
import { OpdrachtForm } from './OpdrachtForm';
import { Badge } from '@/components/common/Badge';
import {
  OPDRACHT_TYPE_LABELS,
  OPDRACHT_STATUS_LABELS,
  OPDRACHT_STATUS_COLORS,
  OPDRACHT_TYPE_COLORS,
  KOSTENSOORT_LABELS,
  OpdrachtType,
  OpdrachtStatus,
  Kostensoort,
} from '@/types';
import { formatCurrency } from '@/utils/format';

interface OpdrachtDetailProps {
  opdrachtId: string;
  onBack: () => void;
}

export function OpdrachtDetail({ opdrachtId, onBack }: OpdrachtDetailProps) {
  const { data: opdracht, isLoading } = useOpdracht(opdrachtId);
  const deleteMutation = useDeleteOpdracht();
  const [editing, setEditing] = useState(false);

  if (isLoading) {
    return <div className="text-center py-8 text-text-secondary">Laden...</div>;
  }

  if (!opdracht) {
    return <div className="text-center py-8 text-text-secondary">Opdracht niet gevonden</div>;
  }

  if (editing) {
    return (
      <OpdrachtForm
        opdracht={opdracht}
        onClose={() => setEditing(false)}
        onSuccess={() => setEditing(false)}
      />
    );
  }

  const uitnutting = opdracht.budget && opdracht.budget > 0
    ? ((opdracht.gerealiseerd || 0) / opdracht.budget * 100)
    : null;

  const handleDelete = async () => {
    if (window.confirm('Weet je zeker dat je deze opdracht wilt verwijderen?')) {
      await deleteMutation.mutateAsync(opdrachtId);
      onBack();
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text transition-colors">
          <ArrowLeft className="h-4 w-4" />
          Terug naar overzicht
        </button>
        <div className="flex items-center gap-2">
          <button onClick={() => setEditing(true)} className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-border hover:bg-gray-50 transition-colors">
            <Edit2 className="h-3.5 w-3.5" />
            Bewerken
          </button>
          <button onClick={handleDelete} className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-red-200 text-red-600 hover:bg-red-50 transition-colors">
            <Trash2 className="h-3.5 w-3.5" />
            Verwijderen
          </button>
        </div>
      </div>

      <div className="bg-surface rounded-xl border border-border p-6">
        <div className="flex items-start justify-between gap-4 mb-4">
          <h2 className="text-xl font-semibold text-text">{opdracht.titel}</h2>
          <div className="flex items-center gap-2 shrink-0">
            <Badge variant={OPDRACHT_TYPE_COLORS[opdracht.type as OpdrachtType] || 'gray'}>
              {OPDRACHT_TYPE_LABELS[opdracht.type as OpdrachtType] || opdracht.type}
            </Badge>
            <Badge variant={OPDRACHT_STATUS_COLORS[opdracht.status as OpdrachtStatus] || 'gray'}>
              {OPDRACHT_STATUS_LABELS[opdracht.status as OpdrachtStatus] || opdracht.status}
            </Badge>
          </div>
        </div>

        {opdracht.beschrijving && (
          <p className="text-sm text-text-secondary mb-6">{opdracht.beschrijving}</p>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-text">Details</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-text-secondary">Begrotingsjaar</dt>
                <dd className="text-text font-medium">{opdracht.begrotingsjaar}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-text-secondary">Instrument</dt>
                <dd className="text-text">{opdracht.instrument?.title || '-'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-text-secondary">Opdrachtnemer</dt>
                <dd className="text-text">{opdracht.opdrachtnemer?.afkorting || opdracht.opdrachtnemer?.naam || '-'}</dd>
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
            <h3 className="text-sm font-semibold text-text">Financieel</h3>
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

        {/* Subsidie-specific */}
        {opdracht.type === 'subsidie' && (opdracht.subsidieregeling || opdracht.beschikking_nummer) && (
          <div className="mt-6 pt-4 border-t border-border">
            <h3 className="text-sm font-semibold text-text mb-2">Subsidie-gegevens</h3>
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
      </div>
    </div>
  );
}
