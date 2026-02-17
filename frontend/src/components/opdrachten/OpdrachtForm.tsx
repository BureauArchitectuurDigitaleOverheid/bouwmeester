import { useState } from 'react';
import { ArrowLeft, X, Plus } from 'lucide-react';
import { useCreateOpdracht, useUpdateOpdracht, useAddOpdrachtNodeKoppeling, useRemoveOpdrachtNodeKoppeling } from '@/hooks/useOpdrachten';
import { useExterneOrganisaties, useCreateExterneOrganisatie } from '@/hooks/useExterneOrganisaties';
import { useNodes } from '@/hooks/useNodes';
import { usePeople } from '@/hooks/usePeople';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { Badge } from '@/components/common/Badge';
import {
  OpdrachtType,
  OpdrachtStatus,
  Kostensoort,
  ExterneOrganisatieType,
  OPDRACHT_TYPE_LABELS,
  OPDRACHT_STATUS_LABELS,
  KOSTENSOORT_LABELS,
  NODE_TYPE_COLORS,
  NodeType,
  type Opdracht,
  type OpdrachtCreate,
  type OpdrachtUpdate,
  type OpdrachtNodeResponse,
} from '@/types';

interface OpdrachtFormProps {
  opdracht?: Opdracht;
  onClose: () => void;
  onSuccess: () => void;
  modal?: boolean;
}

export function OpdrachtForm({ opdracht, onClose, onSuccess, modal = false }: OpdrachtFormProps) {
  const isEdit = !!opdracht;
  const createMutation = useCreateOpdracht();
  const updateMutation = useUpdateOpdracht();
  const createExterneOrg = useCreateExterneOrganisatie();
  const addKoppeling = useAddOpdrachtNodeKoppeling();
  const removeKoppeling = useRemoveOpdrachtNodeKoppeling();
  const { data: externeOrgs = [] } = useExterneOrganisaties();
  const { data: instrumenten = [] } = useNodes(NodeType.INSTRUMENT);
  const { data: allNodes = [] } = useNodes();
  const { data: people = [] } = usePeople();
  const { data: eenheden = [] } = useOrganisatieFlat();

  const [error, setError] = useState<string | null>(null);

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

  const [koppelingen, setKoppelingen] = useState<OpdrachtNodeResponse[]>(opdracht?.node_koppelingen || []);
  const [newKoppelingNodeId, setNewKoppelingNodeId] = useState('');
  const [newKoppelingRelatie, setNewKoppelingRelatie] = useState('gerelateerd');

  const instrumentOptions: SelectOption[] = instrumenten.map(n => ({
    value: n.id,
    label: n.title,
  }));

  const opdrachtnemerOptions: SelectOption[] = externeOrgs.map(o => ({
    value: o.id,
    label: o.afkorting || o.naam,
    description: o.afkorting ? o.naam : undefined,
  }));

  const verantwoordelijkeOptions: SelectOption[] = people.map(p => ({
    value: p.id,
    label: p.naam,
  }));

  const opdrachtgeverOptions: SelectOption[] = eenheden.map(e => ({
    value: e.id,
    label: e.naam,
  }));

  const handleCreateOpdrachtnemer = async (text: string): Promise<string | null> => {
    const result = await createExterneOrg.mutateAsync({
      naam: text,
      type: ExterneOrganisatieType.OVERIG,
    });
    return result?.id || null;
  };

  const nodeOptions: SelectOption[] = allNodes
    .filter(n => !koppelingen.some(k => k.node_id === n.id))
    .map(n => ({
      value: n.id,
      label: n.title,
      description: n.node_type,
    }));

  const handleAddKoppeling = async () => {
    if (!newKoppelingNodeId || !opdracht) return;
    const result = await addKoppeling.mutateAsync({
      opdrachtId: opdracht.id,
      data: { node_id: newKoppelingNodeId, relatie_type: newKoppelingRelatie },
    });
    const selectedNode = allNodes.find(n => n.id === newKoppelingNodeId);
    setKoppelingen(prev => [...prev, {
      ...result,
      node_title: selectedNode?.title || null,
      node_type: selectedNode?.node_type || null,
    }]);
    setNewKoppelingNodeId('');
  };

  const handleRemoveKoppeling = async (koppelingId: string) => {
    if (!opdracht) return;
    await removeKoppeling.mutateAsync({ opdrachtId: opdracht.id, koppelingId });
    setKoppelingen(prev => prev.filter(k => k.id !== koppelingId));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.instrument_id) return;
    setError(null);
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
      opdrachtnemer_id: form.opdrachtnemer_id || null,
      opdrachtgever_id: form.opdrachtgever_id || null,
      verantwoordelijke_id: form.verantwoordelijke_id || null,
      subsidieregeling: form.subsidieregeling || undefined,
      beschikking_nummer: form.beschikking_nummer || undefined,
      status: form.status as OpdrachtStatus,
      referentie: form.referentie || undefined,
      startdatum: form.startdatum || undefined,
      einddatum: form.einddatum || undefined,
    };

    try {
      if (isEdit && opdracht) {
        await updateMutation.mutateAsync({ id: opdracht.id, data: data as OpdrachtUpdate });
      } else {
        await createMutation.mutateAsync(data as OpdrachtCreate);
      }
      onSuccess();
    } catch {
      setError(isEdit ? 'Fout bij opslaan van opdracht.' : 'Fout bij aanmaken van opdracht.');
    }
  };

  const isSubsidie = form.type === OpdrachtType.SUBSIDIE;

  const formContent = (
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
        <CreatableSelect
          label="Instrument"
          required
          value={form.instrument_id}
          onChange={(value) => setForm(f => ({ ...f, instrument_id: value }))}
          options={instrumentOptions}
          placeholder="Kies instrument..."
        />
        <CreatableSelect
          label="Opdrachtnemer"
          value={form.opdrachtnemer_id}
          onChange={(value) => setForm(f => ({ ...f, opdrachtnemer_id: value }))}
          options={opdrachtnemerOptions}
          placeholder="Kies opdrachtnemer..."
          onCreate={handleCreateOpdrachtnemer}
          createLabel="Nieuwe organisatie"
          onClear={() => setForm(f => ({ ...f, opdrachtnemer_id: '' }))}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <CreatableSelect
          label="Opdrachtgever"
          value={form.opdrachtgever_id}
          onChange={(value) => setForm(f => ({ ...f, opdrachtgever_id: value }))}
          options={opdrachtgeverOptions}
          placeholder="Kies opdrachtgever..."
          onClear={() => setForm(f => ({ ...f, opdrachtgever_id: '' }))}
        />
        <CreatableSelect
          label="Verantwoordelijke"
          value={form.verantwoordelijke_id}
          onChange={(value) => setForm(f => ({ ...f, verantwoordelijke_id: value }))}
          options={verantwoordelijkeOptions}
          placeholder="Kies verantwoordelijke..."
          onClear={() => setForm(f => ({ ...f, verantwoordelijke_id: '' }))}
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-text mb-1">Referentie</label>
        <input type="text" value={form.referentie} onChange={e => setForm(f => ({ ...f, referentie: e.target.value }))} className="w-full px-3 py-2 text-sm rounded-lg border border-border" placeholder="Intern kenmerk" />
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

      {/* Node koppelingen (edit mode only) */}
      {isEdit && opdracht && (
        <div className="border-t border-border pt-4">
          <h3 className="text-sm font-semibold text-text mb-3">Gekoppelde nodes</h3>
          {koppelingen.length > 0 && (
            <div className="space-y-1 mb-3">
              {koppelingen.map(k => (
                <div key={k.id} className="flex items-center gap-2 p-1.5 rounded-lg bg-gray-50">
                  {k.node_type && (
                    <Badge variant={NODE_TYPE_COLORS[k.node_type as NodeType] ?? 'gray'} dot>
                      {k.node_type}
                    </Badge>
                  )}
                  <span className="text-sm text-text truncate">{k.node_title || k.node_id}</span>
                  {k.relatie_type && (
                    <span className="text-xs text-text-secondary">{k.relatie_type}</span>
                  )}
                  <button
                    type="button"
                    onClick={() => handleRemoveKoppeling(k.id)}
                    className="ml-auto shrink-0 p-1 rounded hover:bg-gray-200 transition-colors"
                    title="Koppeling verwijderen"
                  >
                    <X className="h-3.5 w-3.5 text-text-secondary" />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <CreatableSelect
                label="Node"
                value={newKoppelingNodeId}
                onChange={setNewKoppelingNodeId}
                options={nodeOptions}
                placeholder="Zoek node..."
              />
            </div>
            <div className="w-40">
              <label className="block text-sm font-medium text-text mb-1">Relatie</label>
              <select
                value={newKoppelingRelatie}
                onChange={e => setNewKoppelingRelatie(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-lg border border-border"
              >
                <option value="gerelateerd">Gerelateerd</option>
                <option value="levert_aan">Levert aan</option>
                <option value="onderdeel_van">Onderdeel van</option>
              </select>
            </div>
            <button
              type="button"
              onClick={handleAddKoppeling}
              disabled={!newKoppelingNodeId || addKoppeling.isPending}
              className="px-3 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors flex items-center gap-1"
            >
              <Plus className="h-4 w-4" />
              Toevoegen
            </button>
          </div>
        </div>
      )}

      {/* Error feedback */}
      {error && (
        <div className="p-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg">
          {error}
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
  );

  if (modal) {
    return formContent;
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <button onClick={onClose} className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text transition-colors">
        <ArrowLeft className="h-4 w-4" />
        Terug naar overzicht
      </button>

      <div className="bg-surface rounded-xl border border-border p-6">
        <h2 className="text-lg font-semibold text-text mb-6">{isEdit ? 'Opdracht bewerken' : 'Nieuwe opdracht'}</h2>
        {formContent}
      </div>
    </div>
  );
}
