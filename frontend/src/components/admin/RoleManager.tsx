import { useState, useMemo } from 'react';
import { Plus, Trash2, ChevronDown, ChevronRight, Shield } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { usePeople } from '@/hooks/usePeople';
import { isPersonOnline, formatRelativeTime } from '@/utils/people';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import {
  useRoles,
  usePersonRoleAssignments,
  useAssignRole,
  useRevokeRole,
} from '@/hooks/useRoles';
import type { PersonRoleAssignment } from '@/hooks/useRoles';
import {
  usePersonResourcePermissions,
  useRemovePersonResourcePermission,
} from '@/hooks/useResourcePermissions';
import type { PersonResourcePermission } from '@/hooks/useResourcePermissions';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { apiGet, apiPost } from '@/api/client';
import { queryKeys } from '@/hooks/queryKeys';

function AssignmentRow({
  assignment,
  onRevoke,
  revoking,
}: {
  assignment: PersonRoleAssignment;
  onRevoke: (id: string) => void;
  revoking: boolean;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <tr className="hover:bg-white/50 transition-colors">
      <td className="px-4 py-1.5 text-text text-sm">
        {assignment.role_naam || assignment.role_id}
      </td>
      <td className="px-4 py-1.5 text-text-secondary text-sm hidden sm:table-cell">
        {assignment.organisatie_eenheid_naam || '-'}
      </td>
      <td className="px-4 py-1.5 text-text-secondary text-sm hidden md:table-cell">
        {new Date(assignment.start_datum).toLocaleDateString('nl-NL')}
      </td>
      <td className="px-4 py-1.5 text-text-secondary text-sm hidden md:table-cell">
        {assignment.eind_datum
          ? new Date(assignment.eind_datum).toLocaleDateString('nl-NL')
          : '-'}
      </td>
      <td className="px-4 py-2">
        {confirmDelete ? (
          <div className="flex items-center gap-1">
            <button
              onClick={() => {
                onRevoke(assignment.id);
                setConfirmDelete(false);
              }}
              disabled={revoking}
              className="px-2 py-0.5 text-xs font-medium rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
            >
              Ja
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="px-2 py-0.5 text-xs font-medium rounded bg-gray-200 text-text hover:bg-gray-300 transition-colors"
            >
              Nee
            </button>
          </div>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            className="p-1 rounded hover:bg-red-50 text-text-secondary hover:text-red-600 transition-colors"
            title="Intrekken"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </td>
    </tr>
  );
}

function PersonRolesPanel({
  personId,
}: {
  personId: string;
}) {
  const { data: assignments, isLoading } = usePersonRoleAssignments(personId);
  const { data: roles } = useRoles();
  const { data: orgUnits } = useOrganisatieFlat();
  const assignRole = useAssignRole();
  const revokeRole = useRevokeRole();

  const [showForm, setShowForm] = useState(false);
  const [selectedRoleId, setSelectedRoleId] = useState('');
  const [selectedOrgId, setSelectedOrgId] = useState('');
  const [startDatum, setStartDatum] = useState('');
  const [eindDatum, setEindDatum] = useState('');

  const selectedRole = roles?.find((r) => r.id === selectedRoleId);
  const isSystemLevel = selectedRole?.level === 'system';

  const handleAssign = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRoleId) return;

    assignRole.mutate(
      {
        person_id: personId,
        role_id: selectedRoleId,
        organisatie_eenheid_id:
          isSystemLevel ? undefined : selectedOrgId || undefined,
        start_datum: startDatum || undefined,
        eind_datum: eindDatum || undefined,
      },
      {
        onSuccess: () => {
          setSelectedRoleId('');
          setSelectedOrgId('');
          setStartDatum('');
          setEindDatum('');
          setShowForm(false);
        },
      },
    );
  };

  const handleRevoke = (assignmentId: string) => {
    revokeRole.mutate(assignmentId);
  };

  if (isLoading) {
    return (
      <div className="bg-gray-50 border-l-3 border-l-primary-300 py-3 px-2">
        <div className="px-4 py-2 text-sm text-text-secondary animate-pulse">
          Laden...
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-50 border-l-3 border-l-primary-300 py-3 px-2">
      <div className="px-4 pb-1.5">
        <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wider">
          Rollen
        </h4>
      </div>
      {/* Current assignments table */}
      {assignments && assignments.length > 0 ? (
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="text-left px-4 py-1.5 font-medium text-text-secondary text-xs">
                Rol
              </th>
              <th className="text-left px-4 py-1.5 font-medium text-text-secondary text-xs hidden sm:table-cell">
                Eenheid
              </th>
              <th className="text-left px-4 py-1.5 font-medium text-text-secondary text-xs hidden md:table-cell">
                Vanaf
              </th>
              <th className="text-left px-4 py-1.5 font-medium text-text-secondary text-xs hidden md:table-cell">
                Tot
              </th>
              <th className="w-10 px-4 py-1.5"></th>
            </tr>
          </thead>
          <tbody>
            {assignments.map((a) => (
              <AssignmentRow
                key={a.id}
                assignment={a}
                onRevoke={handleRevoke}
                revoking={revokeRole.isPending}
              />
            ))}
          </tbody>
        </table>
      ) : (
        <div className="px-4 py-2 text-sm text-text-secondary">
          Geen rollen.
        </div>
      )}

      {/* Add role button / form — directly after roles */}
      {!showForm ? (
        <div className="px-4 py-1.5">
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-1.5 text-sm text-primary-600 hover:text-primary-700 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            Rol toewijzen
          </button>
        </div>
      ) : (
        <form
          onSubmit={handleAssign}
          className="px-4 py-3 space-y-3"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Role selector */}
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">
                Rol
              </label>
              <select
                value={selectedRoleId}
                onChange={(e) => {
                  setSelectedRoleId(e.target.value);
                  // Reset org when switching to system role
                  const role = roles?.find((r) => r.id === e.target.value);
                  if (role?.level === 'system') setSelectedOrgId('');
                }}
                className="w-full px-3 py-1.5 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400 bg-white"
                required
              >
                <option value="">Kies een rol...</option>
                {roles?.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.naam}
                    {role.description ? ` - ${role.description}` : ''}
                  </option>
                ))}
              </select>
            </div>

            {/* Org unit selector (hidden for system roles) */}
            {!isSystemLevel && (
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">
                  Organisatie-eenheid
                </label>
                <select
                  value={selectedOrgId}
                  onChange={(e) => setSelectedOrgId(e.target.value)}
                  className="w-full px-3 py-1.5 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400 bg-white"
                  required={!!selectedRoleId && !isSystemLevel}
                >
                  <option value="">Kies een eenheid...</option>
                  {orgUnits?.map((unit) => (
                    <option key={unit.id} value={unit.id}>
                      {unit.naam}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Start date */}
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">
                Startdatum (optioneel)
              </label>
              <input
                type="date"
                value={startDatum}
                onChange={(e) => setStartDatum(e.target.value)}
                className="w-full px-3 py-1.5 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400 bg-white"
              />
            </div>

            {/* End date */}
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">
                Einddatum (optioneel)
              </label>
              <input
                type="date"
                value={eindDatum}
                onChange={(e) => setEindDatum(e.target.value)}
                className="w-full px-3 py-1.5 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400 bg-white"
              />
            </div>
          </div>

          <div className="flex gap-2">
            <button
              type="submit"
              disabled={assignRole.isPending || !selectedRoleId}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              Toewijzen
            </button>
            <button
              type="button"
              onClick={() => {
                setShowForm(false);
                setSelectedRoleId('');
                setSelectedOrgId('');
                setStartDatum('');
                setEindDatum('');
              }}
              className="px-3 py-1.5 text-sm font-medium rounded-lg bg-gray-200 text-text hover:bg-gray-300 transition-colors"
            >
              Annuleren
            </button>
          </div>
        </form>
      )}

      {/* Resource permissions */}
      <PersonResourcePermissionsSection personId={personId} />
    </div>
  );
}

const RESOURCE_TYPE_LABELS: Record<string, string> = {
  corpus_node: 'Beleidsobject',
  initiatief: 'Initiatief',
  lead: 'Lead',
  team: 'Team',
  opdracht: 'Opdracht',
};

function ResourcePermissionRow({
  rp,
  onRemove,
  removing,
}: {
  rp: PersonResourcePermission;
  onRemove: (id: string) => void;
  removing: boolean;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <tr className="hover:bg-white/50 transition-colors">
      <td className="px-4 py-1.5 text-text text-sm">
        {rp.resource_name}
      </td>
      <td className="px-4 py-1.5 text-text-secondary text-sm hidden sm:table-cell">
        {RESOURCE_TYPE_LABELS[rp.resource_type] || rp.resource_type}
      </td>
      <td className="px-4 py-1.5 text-text-secondary text-sm">
        {rp.rol}
      </td>
      <td className="px-4 py-2">
        {confirmDelete ? (
          <div className="flex items-center gap-1">
            <button
              onClick={() => {
                onRemove(rp.id);
                setConfirmDelete(false);
              }}
              disabled={removing}
              className="px-2 py-0.5 text-xs font-medium rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
            >
              Ja
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="px-2 py-0.5 text-xs font-medium rounded bg-gray-200 text-text hover:bg-gray-300 transition-colors"
            >
              Nee
            </button>
          </div>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            className="p-1 rounded hover:bg-red-50 text-text-secondary hover:text-red-600 transition-colors"
            title="Verwijderen"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </td>
    </tr>
  );
}

const RESOURCE_ROLE_OPTIONS = [
  { value: 'eigenaar', label: 'Eigenaar' },
  { value: 'betrokken', label: 'Betrokken' },
  { value: 'adviseur', label: 'Adviseur' },
  { value: 'contributor', label: 'Contributor' },
];

const RESOURCE_TYPE_OPTIONS = [
  { value: 'corpus_node', label: 'Beleidsobject' },
  { value: 'initiatief', label: 'Initiatief' },
  { value: 'lead', label: 'Lead' },
  { value: 'opdracht', label: 'Opdracht' },
];

interface ResourceOption {
  id: string;
  label: string;
}

const RESOURCE_API_MAP: Record<string, { url: string; map: (item: Record<string, unknown>) => ResourceOption }> = {
  corpus_node: { url: '/api/nodes', map: (n) => ({ id: n.id as string, label: n.title as string }) },
  initiatief: { url: '/api/initiatieven', map: (i) => ({ id: i.id as string, label: i.naam as string }) },
  lead: { url: '/api/leads', map: (l) => ({ id: l.id as string, label: l.title as string }) },
  opdracht: { url: '/api/opdrachten', map: (o) => ({ id: o.id as string, label: o.titel as string }) },
};

function useResourceOptions(resourceType: string) {
  const config = RESOURCE_API_MAP[resourceType];
  const { data } = useQuery({
    queryKey: ['resource-options', resourceType],
    queryFn: () => apiGet<Record<string, unknown>[]>(config.url),
    enabled: !!config,
    staleTime: 60_000,
  });

  return useMemo(
    () => (data ?? []).map(config?.map ?? (() => ({ id: '', label: '' }))),
    [data, config],
  );
}

function PersonResourcePermissionsSection({ personId }: { personId: string }) {
  const { data: perms } = usePersonResourcePermissions(personId);
  const removeRp = useRemovePersonResourcePermission(personId);
  const queryClient = useQueryClient();

  const [showForm, setShowForm] = useState(false);
  const [selectedResourceType, setSelectedResourceType] = useState('');
  const [selectedResourceId, setSelectedResourceId] = useState('');
  const [selectedRol, setSelectedRol] = useState('');

  const resourceOptions = useResourceOptions(selectedResourceType);

  const addPermission = useMutationWithError({
    mutationFn: (data: {
      resourceType: string;
      resourceId: string;
      person_id: string;
      rol: string;
    }) =>
      apiPost(
        `/api/resource-permissions/${data.resourceType}/${data.resourceId}`,
        { person_id: data.person_id, rol: data.rol },
      ),
    errorMessage: 'Fout bij toevoegen resource permissie',
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.admin.personResourcePermissions(personId),
      });
    },
  });

  const resetForm = () => {
    setSelectedResourceType('');
    setSelectedResourceId('');
    setSelectedRol('');
    setShowForm(false);
  };

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedResourceType || !selectedResourceId || !selectedRol) return;

    addPermission.mutate(
      {
        resourceType: selectedResourceType,
        resourceId: selectedResourceId,
        person_id: personId,
        rol: selectedRol,
      },
      { onSuccess: resetForm },
    );
  };

  const hasPerms = perms && perms.length > 0;

  return (
    <div className="mt-3 pt-3 border-t border-gray-200/80">
      <div className="px-4 pb-1.5">
        <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wider">
          Resource permissies
        </h4>
      </div>
      {hasPerms && (
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="text-left px-4 py-1.5 font-medium text-text-secondary text-xs">
                Naam
              </th>
              <th className="text-left px-4 py-1.5 font-medium text-text-secondary text-xs hidden sm:table-cell">
                Type
              </th>
              <th className="text-left px-4 py-1.5 font-medium text-text-secondary text-xs">
                Rol
              </th>
              <th className="w-10 px-4 py-1.5"></th>
            </tr>
          </thead>
          <tbody>
            {perms.map((rp) => (
              <ResourcePermissionRow
                key={rp.id}
                rp={rp}
                onRemove={(id) => removeRp.mutate(id)}
                removing={removeRp.isPending}
              />
            ))}
          </tbody>
        </table>
      )}
      {!hasPerms && !showForm && (
        <div className="px-4 py-2 text-sm text-text-secondary">
          Geen resource permissies.
        </div>
      )}

      {!showForm ? (
        <div className="px-4 py-1.5">
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-1.5 text-sm text-primary-600 hover:text-primary-700 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            Resource permissie toevoegen
          </button>
        </div>
      ) : (
        <form
          onSubmit={handleAdd}
          className="px-4 py-3 space-y-3"
        >
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">
                Resource type
              </label>
              <select
                value={selectedResourceType}
                onChange={(e) => {
                  setSelectedResourceType(e.target.value);
                  setSelectedResourceId('');
                }}
                className="w-full px-3 py-1.5 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400 bg-white"
                required
              >
                <option value="">Kies type...</option>
                {RESOURCE_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">
                Resource
              </label>
              <select
                value={selectedResourceId}
                onChange={(e) => setSelectedResourceId(e.target.value)}
                className="w-full px-3 py-1.5 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400 bg-white"
                required
                disabled={!selectedResourceType}
              >
                <option value="">
                  {selectedResourceType
                    ? 'Kies resource...'
                    : 'Kies eerst type'}
                </option>
                {resourceOptions.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">
                Rol
              </label>
              <select
                value={selectedRol}
                onChange={(e) => setSelectedRol(e.target.value)}
                className="w-full px-3 py-1.5 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400 bg-white"
                required
              >
                <option value="">Kies rol...</option>
                {RESOURCE_ROLE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex gap-2">
            <button
              type="submit"
              disabled={
                addPermission.isPending ||
                !selectedResourceType ||
                !selectedResourceId ||
                !selectedRol
              }
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              Toevoegen
            </button>
            <button
              type="button"
              onClick={resetForm}
              className="px-3 py-1.5 text-sm font-medium rounded-lg bg-gray-200 text-text hover:bg-gray-300 transition-colors"
            >
              Annuleren
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

export function RoleManager() {
  const { data: people, isLoading: loadingPeople } = usePeople();
  const { data: roles, isLoading: loadingRoles } = useRoles();
  const [expandedPersonId, setExpandedPersonId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredPeople = useMemo(() => {
    if (!people) return [];
    const q = searchQuery.toLowerCase().trim();
    if (!q) return people;
    return people.filter(
      (p) =>
        p.naam.toLowerCase().includes(q) ||
        (p.email && p.email.toLowerCase().includes(q)) ||
        (p.functie && p.functie.toLowerCase().includes(q)),
    );
  }, [people, searchQuery]);

  if (loadingPeople || loadingRoles) {
    return (
      <div className="text-sm text-text-secondary py-8 text-center">
        Laden...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Description */}
      <div className="flex items-start gap-2 text-sm text-text-secondary">
        <Shield className="h-4 w-4 mt-0.5 shrink-0 text-primary-500" />
        <span>
          Beheer roltoewijzingen per persoon. Klik op een persoon om rollen te
          bekijken, toe te wijzen of in te trekken.
          {roles && roles.length > 0 && (
            <>
              {' '}
              Beschikbare rollen:{' '}
              {roles.map((r) => r.naam).join(', ')}.
            </>
          )}
        </span>
      </div>

      {/* Search */}
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder="Zoek op naam, e-mail of functie..."
        className="w-full px-3 py-2 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
      />

      {/* People list with expandable role panels */}
      <div className="border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-border">
              <th className="w-8 px-3 py-2.5"></th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary">
                Naam
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden sm:table-cell">
                E-mail
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden md:table-cell">
                Functie
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden lg:table-cell">
                Laatst actief
              </th>
            </tr>
          </thead>
          <tbody>
            {filteredPeople.map((person) => {
              const isExpanded = expandedPersonId === person.id;
              return (
                <PersonRow
                  key={person.id}
                  personId={person.id}
                  naam={person.naam}
                  email={person.email}
                  functie={person.functie}
                  lastSeenAt={person.last_seen_at}
                  isAgent={person.is_agent}
                  isExpanded={isExpanded}
                  onToggle={() =>
                    setExpandedPersonId(isExpanded ? null : person.id)
                  }
                />
              );
            })}
            {filteredPeople.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-4 py-8 text-center text-text-secondary"
                >
                  {searchQuery
                    ? 'Geen personen gevonden'
                    : 'Geen personen beschikbaar'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PersonRow({
  personId,
  naam,
  email,
  functie,
  lastSeenAt,
  isAgent,
  isExpanded,
  onToggle,
}: {
  personId: string;
  naam: string;
  email?: string;
  functie?: string;
  lastSeenAt?: string | null;
  isAgent?: boolean;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const online = isPersonOnline({ last_seen_at: lastSeenAt, is_agent: isAgent });

  return (
    <>
      <tr
        onClick={onToggle}
        className="border-b border-border last:border-b-0 hover:bg-gray-50 transition-colors cursor-pointer"
      >
        <td className="px-3 py-2.5 text-text-secondary">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </td>
        <td className="px-4 py-2.5 text-text">{naam}</td>
        <td className="px-4 py-2.5 text-text-secondary hidden sm:table-cell">
          {email || '-'}
        </td>
        <td className="px-4 py-2.5 text-text-secondary hidden md:table-cell">
          {functie || '-'}
        </td>
        <td className="px-4 py-2.5 text-text-secondary hidden lg:table-cell">
          {online ? (
            <span className="inline-flex items-center gap-1.5 text-green-600">
              <span className="block h-2 w-2 rounded-full bg-green-500" />
              Nu actief
            </span>
          ) : (
            formatRelativeTime(lastSeenAt)
          )}
        </td>
      </tr>
      {isExpanded && (
        <tr className="border-b-2 border-primary-200">
          <td colSpan={5} className="p-0">
            <PersonRolesPanel personId={personId} />
          </td>
        </tr>
      )}
    </>
  );
}
