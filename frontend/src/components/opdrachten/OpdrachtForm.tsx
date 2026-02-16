import { useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useCreateOpdracht, useUpdateOpdracht } from '@/hooks/useOpdrachten';
import { useExterneOrganisaties } from '@/hooks/useExterneOrganisaties';
import { useNodes } from '@/hooks/useNodes';
import { useOrganisatieTree } from '@/hooks/useOrganisatie';
import { usePeople } from '@/hooks/usePeople';
import {
  OpdrachtType,
  OpdrachtStatus,
  Kostensoort,
  OPDRACHT_TYPE_LABELS,
  OPDRACHT_STATUS_LABELS,
  KOSTENSOORT_LABELS,
  NodeType,
  type Opdracht,
  type OpdrachtCreate,
  type OpdrachtUpdate,
} from '@/types';

interface OpdrachtFormProps {
  opdracht?: Opdracht;
  onClose: () => void;
  onSuccess: () => void;
}

export function OpdrachtForm({ opdracht, onClose, onSuccess }: OpdrachtFormProps) {
  const isEdit = !!opdracht;
  const createMutation = useCreateOpdracht();
  const updateMutation = useUpdateOpdracht();
  const { data: externeOrgs = [] } = useExterneOrganisaties();
  const { data: instrumenten = [] } = useNodes(NodeType.INSTRUMENT);
  const { data: people = [] } = usePeople();

  const [form, setForm] = useState({
    type: opdracht?.type || OpdrachtType.OPDRACHT,
    titel: opdracht?.titel || '',
    beschrijving: opdracht?.beschrijving || '',
    begrotingsjaar: opdracht?.begrotingsjaar || new Date().getFullYear(),
    budget: opdracht?.budget?.toString() || '',
    gerealiseerd: opdracht?.gerealiseerd?.toString() || '',
    kostensoort: opdracht?.kostensoort || '',
    volgend_jaar_benodigd: opdracht?.volgend_jaar_benodigd?.toString() || '',
    volgend_jaar_aangevraagd: opdracht?.volgend_jaar_aangevraagd?.toString() || '',
    instrument_id: opdracht?.instrument_id || '',
    opdrachtnemer_id: opdracht?.opdrachtnemer_id || '',
    opdrachtgever_id: opdracht?.opdrachtgever_id || '',
    verantwoordelijke_id: opdracht?.verantwoordelijke_id || '',
    subsidieregeling: opdracht?.subsidieregeling || '',
    beschikking_nummer: opdracht?.beschikking_nummer || '',
    status: opdracht?.status || OpdrachtStatus.CONCEPT,
    referentie: opdracht?.referentie || '',
    startdatum: opdracht?.startdatum || '',
    einddatum: opdracht?.einddatum || '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const data = {
      type: form.type as OpdrachtType,
      titel: form.titel,
      beschrijving: form.beschrijving || undefined,
      begrotingsjaar: form.begrotingsjaar,
      budget: form.budget ? Number(form.budget) : undefined,
      gerealiseerd: form.gerealiseerd ? Number(form.gerealiseerd) : undefined,
      kostensoort: form.kostensoort ? (form.kostensoort as Kostensoort) : undefined,
      volgend_jaar_benodigd: form.volgend_jaar_benodigd ? Number(form.volgend_jaar_benodigd) : undefined,
      volgend_jaar_aangevraagd: form.volgend_jaar_aangevraagd ? Number(form.volgend_jaar_aangevraagd) : undefined,
      instrument_id: form.instrument_id,
      opdrachtnemer_id: form.opdrachtnemer_id || undefined,
      opdrachtgever_id: form.opdrachtgever_id || undefined,
      verantwoordelijke_id: form.verantwoordelijke_id || undefined,
      subsidieregeling: form.subsidieregeling || undefined,
      beschikking_nummer: form.beschikking_nummer || undefined,
      status: form.status as OpdrachtStatus,
      referentie: form.referentie || undefined,
      startdatum: form.startdatum || undefined,
      einddatum: form.einddatum || undefined,
    };

    if (isEdit && opdracht) {
      await updateMutation.mutateAsync({ id: opdracht.id, data: data as OpdrachtUpdate });
    } else {
      await createMutation.mutateAsync(data as OpdrachtCreate);
    }
    onSuccess();
  };

  const isSubsidie = form.type === OpdrachtType.SUBSIDIE;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <button onClick={onClose} className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text transition-colors">
        <ArrowLeft className="h-4 w-4" />
        Terug naar overzicht
      </button>

      <div className="bg-surface rounded-xl border border-border p-6">
        <h2 className="text-lg font-semibold text-text mb-6">{isEdit ? 'Opdracht bewerken' : 'Nieuwe opdracht'}</h2>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basic info */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-text mb-1">Type *</label>
              <select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-lg border border-border">
                {Object.entries(OPDRACHT_TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-text mb-1">Status</label>
              <select value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-lg border border-border">
                {Object.entries(OPDRACHT_STATUS_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text mb-1">Titel *</label>
            <input type="text" value={form.titel} onChange={e => setForm(f => ({ ...f, titel: e.target.value }))} required className="w-full px-3 py-2 text-sm rounded-lg border border-border" />
          </div>

          <div>
            <label className="block text-sm font-medium text-text mb-1">Beschrijving</label>
            <textarea value={form.beschrijving} onChange={e => setForm(f => ({ ...f, beschrijving: e.target.value }))} rows={3} className="w-full px-3 py-2 text-sm rounded-lg border border-border" />
          </div>

          {/* Links */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-text mb-1">Instrument *</label>
              <select value={form.instrument_id} onChange={e => setForm(f => ({ ...f, instrument_id: e.target.value }))} required className="w-full px-3 py-2 text-sm rounded-lg border border-border">
                <option value="">Kies instrument...</option>
                {instrumenten.map(n => <option key={n.id} value={n.id}>{n.title}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-text mb-1">Opdrachtnemer</label>
              <select value={form.opdrachtnemer_id} onChange={e => setForm(f => ({ ...f, opdrachtnemer_id: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-lg border border-border">
                <option value="">Kies opdrachtnemer...</option>
                {externeOrgs.map(o => <option key={o.id} value={o.id}>{o.afkorting || o.naam}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-text mb-1">Verantwoordelijke</label>
              <select value={form.verantwoordelijke_id} onChange={e => setForm(f => ({ ...f, verantwoordelijke_id: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-lg border border-border">
                <option value="">Kies verantwoordelijke...</option>
                {people.map(p => <option key={p.id} value={p.id}>{p.naam}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-text mb-1">Referentie</label>
              <input type="text" value={form.referentie} onChange={e => setForm(f => ({ ...f, referentie: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-lg border border-border" placeholder="Intern kenmerk" />
            </div>
          </div>

          {/* Financial */}
          <div className="border-t border-border pt-4">
            <h3 className="text-sm font-semibold text-text mb-3">Financieel</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-text mb-1">Begrotingsjaar *</label>
                <input type="number" value={form.begrotingsjaar} onChange={e => setForm(f => ({ ...f, begrotingsjaar: Number(e.target.value) }))} min={2020} max={2035} required className="w-full px-3 py-2 text-sm rounded-lg border border-border" />
              </div>
              <div>
                <label className="block text-sm font-medium text-text mb-1">Budget</label>
                <input type="number" value={form.budget} onChange={e => setForm(f => ({ ...f, budget: e.target.value }))} min={0} step="0.01" className="w-full px-3 py-2 text-sm rounded-lg border border-border" />
              </div>
              <div>
                <label className="block text-sm font-medium text-text mb-1">Gerealiseerd</label>
                <input type="number" value={form.gerealiseerd} onChange={e => setForm(f => ({ ...f, gerealiseerd: e.target.value }))} min={0} step="0.01" className="w-full px-3 py-2 text-sm rounded-lg border border-border" />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
              <div>
                <label className="block text-sm font-medium text-text mb-1">Kostensoort</label>
                <select value={form.kostensoort} onChange={e => setForm(f => ({ ...f, kostensoort: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-lg border border-border">
                  <option value="">-</option>
                  {Object.entries(KOSTENSOORT_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-text mb-1">Volgend jaar benodigd</label>
                <input type="number" value={form.volgend_jaar_benodigd} onChange={e => setForm(f => ({ ...f, volgend_jaar_benodigd: e.target.value }))} min={0} step="0.01" className="w-full px-3 py-2 text-sm rounded-lg border border-border" />
              </div>
              <div>
                <label className="block text-sm font-medium text-text mb-1">Volgend jaar aangevraagd</label>
                <input type="number" value={form.volgend_jaar_aangevraagd} onChange={e => setForm(f => ({ ...f, volgend_jaar_aangevraagd: e.target.value }))} min={0} step="0.01" className="w-full px-3 py-2 text-sm rounded-lg border border-border" />
              </div>
            </div>
          </div>

          {/* Dates */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-text mb-1">Startdatum</label>
              <input type="date" value={form.startdatum} onChange={e => setForm(f => ({ ...f, startdatum: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-lg border border-border" />
            </div>
            <div>
              <label className="block text-sm font-medium text-text mb-1">Einddatum</label>
              <input type="date" value={form.einddatum} onChange={e => setForm(f => ({ ...f, einddatum: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-lg border border-border" />
            </div>
          </div>

          {/* Subsidie-specific */}
          {isSubsidie && (
            <div className="border-t border-border pt-4">
              <h3 className="text-sm font-semibold text-text mb-3">Subsidie-specifiek</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-text mb-1">Subsidieregeling</label>
                  <input type="text" value={form.subsidieregeling} onChange={e => setForm(f => ({ ...f, subsidieregeling: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-lg border border-border" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-text mb-1">Beschikking nummer</label>
                  <input type="text" value={form.beschikking_nummer} onChange={e => setForm(f => ({ ...f, beschikking_nummer: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-lg border border-border" />
                </div>
              </div>
            </div>
          )}

          {/* Submit */}
          <div className="flex justify-end gap-3 pt-4 border-t border-border">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-border hover:bg-gray-50 transition-colors">
              Annuleren
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending || updateMutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {isEdit ? 'Opslaan' : 'Aanmaken'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
