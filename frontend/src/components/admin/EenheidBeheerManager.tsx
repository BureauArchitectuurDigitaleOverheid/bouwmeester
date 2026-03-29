import { useState, useMemo } from 'react';
import { ChevronRight, ChevronDown, Search, Users, Blocks } from 'lucide-react';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { Badge } from '@/components/common/Badge';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { useEenheidRoleAssignments } from '@/hooks/useRoles';
import {
  useEenheidModules,
  useAvailableModules,
  useUpdateEenheidModule,
} from '@/hooks/useEenheidModules';
import { ORGANISATIE_TYPE_LABELS } from '@/types';

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
        Beheer rollen en modules per organisatie-eenheid. Klik op een eenheid om de details te zien.
      </p>

      {/* Search */}
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

      {/* Table */}
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

// ---------------------------------------------------------------------------
// Eenheid row (expandable)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Detail panel: rollen + modules
// ---------------------------------------------------------------------------

function EenheidDetailPanel({ eenheidId }: { eenheidId: string }) {
  const { data: assignments, isLoading: rolesLoading } = useEenheidRoleAssignments(eenheidId);
  const { data: moduleConfig, isLoading: modulesLoading } = useEenheidModules(eenheidId);
  const { data: moduleLabels } = useAvailableModules();
  const updateModuleMutation = useUpdateEenheidModule();

  const handleToggle = async (module: string, currentEnabled: boolean) => {
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
      {/* Rollen sectie */}
      <div>
        <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5 mb-3">
          <Users className="h-3.5 w-3.5" />
          Rollen in deze eenheid
        </h4>

        {rolesLoading && <LoadingSpinner className="py-4" />}

        {!rolesLoading && assignments && assignments.length === 0 && (
          <p className="text-sm text-text-secondary">Geen roltoewijzingen.</p>
        )}

        {!rolesLoading && assignments && assignments.length > 0 && (
          <div className="rounded-lg border border-border bg-white overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-medium text-text-secondary uppercase tracking-wider bg-gray-50">
                  <th className="px-3 py-2">Persoon</th>
                  <th className="px-3 py-2">Rol</th>
                  <th className="px-3 py-2 hidden md:table-cell">Vanaf</th>
                  <th className="px-3 py-2 hidden md:table-cell">Tot</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {assignments.map((a) => (
                  <tr key={a.id}>
                    <td className="px-3 py-2 text-text">{a.person_naam ?? '—'}</td>
                    <td className="px-3 py-2">
                      <Badge variant="blue">{a.role_naam ?? a.role_id}</Badge>
                    </td>
                    <td className="px-3 py-2 text-text-secondary hidden md:table-cell">
                      {a.start_datum}
                    </td>
                    <td className="px-3 py-2 text-text-secondary hidden md:table-cell">
                      {a.eind_datum ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modules sectie */}
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
                      onClick={() => handleToggle(mod.module, mod.enabled)}
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
