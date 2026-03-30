import { useState, useMemo } from 'react';
import { ChevronRight, ChevronDown, Search, Blocks, Lightbulb, X } from 'lucide-react';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import {
  useInitiatieven,
  useInitiatievenForEenheid,
  useAddInitiatiefEenheid,
  useRemoveInitiatiefEenheid,
  useUpdateInitiatiefEenheidRol,
} from '@/hooks/useInitiatieven';
import {
  useEenheidModules,
  useAvailableModules,
  useUpdateEenheidModule,
} from '@/hooks/useEenheidModules';
import { ORGANISATIE_TYPE_LABELS, INITIATIEF_ROL_LABELS } from '@/types';

const MODULE_DESCRIPTIONS: Record<string, string> = {
  corpus: 'Beleidsdossiers, doelen, instrumenten en hun relaties',
  initiatieven: 'Samenwerkingsinitiatieven met leden en eenheden',
  leads: 'Leads en contacten voor beleidsonderwerpen',
  opdrachten: 'Opdrachten en financieel overzicht',
  taken: 'Taakbeheer gekoppeld aan corpus-items',
};

export function EenheidBeheerManager() {
  const { data: allEenheden = [], isLoading } = useOrganisatieFlat();
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    if (!search.trim()) return allEenheden;
    const q = search.toLowerCase();
    return allEenheden.filter(
      (e) =>
        e.naam.toLowerCase().includes(q) ||
        e.type.toLowerCase().includes(q),
    );
  }, [allEenheden, search]);

  if (isLoading) return <LoadingSpinner className="py-12" />;

  return (
    <div className="space-y-4">
      <p className="text-sm text-text-secondary">
        Beheer initiatieven en modules per organisatie-eenheid. Klik op een eenheid om de details te zien.
      </p>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Zoek op naam..."
          className="w-full rounded-xl border border-border pl-10 pr-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
        />
      </div>

      <div className="border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-left text-xs font-medium text-text-secondary uppercase tracking-wider">
              <th className="pl-4 pr-2 py-2.5 w-8" />
              <th className="px-3 py-2.5">Naam</th>
              <th className="px-3 py-2.5 hidden sm:table-cell">Type</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filtered.map((eenheid) => {
              const isExpanded = expandedId === eenheid.id;
              return (
                <EenheidRow
                  key={eenheid.id}
                  eenheid={eenheid}
                  isExpanded={isExpanded}
                  onToggle={() => setExpandedId(isExpanded ? null : eenheid.id)}
                />
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-8 text-center text-text-secondary">
                  Geen eenheden gevonden.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EenheidRow({
  eenheid,
  isExpanded,
  onToggle,
}: {
  eenheid: { id: string; naam: string; type: string };
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const typeLabel = ORGANISATIE_TYPE_LABELS[eenheid.type] ?? eenheid.type;

  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer hover:bg-gray-50 transition-colors"
      >
        <td className="pl-4 pr-2 py-2.5">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-text-secondary" />
          ) : (
            <ChevronRight className="h-4 w-4 text-text-secondary" />
          )}
        </td>
        <td className="px-3 py-2.5 font-medium text-text">{eenheid.naam}</td>
        <td className="px-3 py-2.5 text-text-secondary hidden sm:table-cell">
          {typeLabel}
        </td>
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={3} className="p-0">
            <EenheidDetailPanel eenheidId={eenheid.id} />
          </td>
        </tr>
      )}
    </>
  );
}

function EenheidDetailPanel({ eenheidId }: { eenheidId: string }) {
  const { data: initiatieven, isLoading: initiativeLoading } = useInitiatievenForEenheid(eenheidId);
  const { data: allInitiatieven } = useInitiatieven();
  const { data: moduleConfig, isLoading: modulesLoading } = useEenheidModules(eenheidId);
  const { data: moduleLabels } = useAvailableModules();
  const updateModuleMutation = useUpdateEenheidModule();
  const addEenheidMutation = useAddInitiatiefEenheid();
  const removeEenheidMutation = useRemoveInitiatiefEenheid();
  const updateRolMutation = useUpdateInitiatiefEenheidRol();

  const [addValue, setAddValue] = useState('');

  const availableInitiatieven = useMemo(() => {
    if (!allInitiatieven || !initiatieven) return [];
    const linkedIds = new Set(initiatieven.map((i) => i.initiatief_id));
    return allInitiatieven
      .filter((i) => !linkedIds.has(i.id))
      .map((i) => ({ value: i.id, label: i.naam }));
  }, [allInitiatieven, initiatieven]);

  const handleAddInitiatief = async (initiatiefId: string) => {
    if (!initiatiefId) return;
    await addEenheidMutation.mutateAsync({ initiatiefId, eenheidId });
    setAddValue('');
  };

  const handleRemoveInitiatief = async (initiatiefId: string) => {
    await removeEenheidMutation.mutateAsync({ initiatiefId, eenheidId });
  };

  const handleRolChange = async (initiatiefId: string, rol: string) => {
    await updateRolMutation.mutateAsync({ initiatiefId, eenheidId, rol });
  };

  const handleModuleToggle = async (module: string, currentEnabled: boolean) => {
    try {
      await updateModuleMutation.mutateAsync({
        eenheidId,
        module,
        enabled: !currentEnabled,
      });
    } catch {
      // error state handled by mutation
    }
  };

  return (
    <div className="bg-gray-50 border-l-[3px] border-l-primary-300 px-6 py-5 space-y-6">
      {/* Initiatieven */}
      <div>
        <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5 mb-3">
          <Lightbulb className="h-3.5 w-3.5" />
          Initiatieven
        </h4>

        {initiativeLoading && <LoadingSpinner className="py-4" />}

        {!initiativeLoading && initiatieven && initiatieven.length > 0 && (
          <ul className="divide-y divide-border rounded-lg border border-border bg-white mb-3">
            {initiatieven.map((link) => (
              <li key={link.initiatief_id} className="flex items-center justify-between px-3 py-2">
                <span className="text-sm text-text truncate">{link.initiatief_naam}</span>
                <div className="flex items-center gap-1.5 shrink-0">
                  <select
                    value={link.rol}
                    onChange={(e) => handleRolChange(link.initiatief_id, e.target.value)}
                    className="text-xs border border-border rounded px-1.5 py-0.5 bg-white"
                  >
                    {Object.entries(INITIATIEF_ROL_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => handleRemoveInitiatief(link.initiatief_id)}
                    className="p-1 rounded hover:bg-gray-100 text-text-secondary hover:text-red-500 transition-colors"
                    title="Ontkoppelen"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {!initiativeLoading && initiatieven && initiatieven.length === 0 && (
          <p className="text-sm text-text-secondary mb-3">Geen gekoppelde initiatieven.</p>
        )}

        <div className="flex items-start gap-2">
          <div className="flex-1 max-w-xs">
            <CreatableSelect
              value={addValue}
              onChange={(val) => {
                setAddValue(val);
                if (val) handleAddInitiatief(val);
              }}
              options={availableInitiatieven}
              placeholder="Initiatief toevoegen..."
              emptyMessage="Geen initiatieven gevonden"
            />
          </div>
        </div>
      </div>

      {/* Modules */}
      <div>
        <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5 mb-3">
          <Blocks className="h-3.5 w-3.5" />
          Modules
        </h4>

        {modulesLoading && <LoadingSpinner className="py-4" />}

        {updateModuleMutation.isError && (
          <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-3">
            Kon module-instelling niet opslaan.
          </p>
        )}

        {!modulesLoading && moduleConfig && (
          <div className="rounded-lg border border-border bg-white divide-y divide-border overflow-hidden">
            {moduleConfig.modules.map((mod) => {
              const isInherited = mod.inherited_from !== null && !mod.enabled;
              const label = moduleLabels?.[mod.module] ?? mod.module;
              const description = MODULE_DESCRIPTIONS[mod.module] ?? '';

              return (
                <div
                  key={mod.module}
                  className="flex items-center justify-between px-3 py-2.5"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-text">{label}</span>
                      {isInherited && (
                        <span className="text-xs text-amber-600 bg-amber-50 rounded px-1.5 py-0.5">
                          Overgenomen van {mod.inherited_from_naam}
                        </span>
                      )}
                    </div>
                    {description && (
                      <p className="text-xs text-text-secondary mt-0.5">{description}</p>
                    )}
                  </div>
                  <div className="shrink-0 ml-4">
                    <button
                      type="button"
                      role="switch"
                      aria-checked={mod.enabled}
                      disabled={isInherited || updateModuleMutation.isPending}
                      onClick={() => handleModuleToggle(mod.module, mod.enabled)}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:ring-offset-2 ${
                        mod.enabled ? 'bg-primary-600' : 'bg-gray-200'
                      } ${isInherited ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                          mod.enabled ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
