import { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus, Building2, Search, X } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { OrganisatieTree } from '@/components/organisatie/OrganisatieTree';
import { OrganisatieDetail } from '@/components/organisatie/OrganisatieDetail';
import { OrganisatieForm } from '@/components/organisatie/OrganisatieForm';
import { PersonEditForm } from '@/components/people/PersonEditForm';
import {
  useOrganisatieTree,
  useCreateOrganisatieEenheid,
  useUpdateOrganisatieEenheid,
  useDeleteOrganisatieEenheid,
} from '@/hooks/useOrganisatie';
import { useAddPersonOrganisatie, usePersonOrganisaties } from '@/hooks/usePeople';
import { usePersonFormSubmit } from '@/hooks/usePersonFormSubmit';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { todayISO } from '@/utils/dates';
import type { OrganisatieEenheid, OrganisatieEenheidCreate, OrganisatieEenheidUpdate, Person } from '@/types';

export function OrganisatiePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get('eenheid'));
  const [showForm, setShowForm] = useState(false);
  const [editData, setEditData] = useState<OrganisatieEenheid | null>(null);
  const [defaultParentId, setDefaultParentId] = useState<string | null>(null);

  // Person form state
  const [showPersonForm, setShowPersonForm] = useState(false);
  const [editPerson, setEditPerson] = useState<Person | null>(null);
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null);

  // Boom-zoek + filters
  const [searchTerm, setSearchTerm] = useState('');
  const [includeHistorisch, setIncludeHistorisch] = useState(false);
  const [bronFilter, setBronFilter] = useState<'alle' | 'handmatig' | 'tooi' | 'scrape'>('alle');

  // Sync ?eenheid= param on arrival, then clear it
  useEffect(() => {
    const eenheidParam = searchParams.get('eenheid');
    if (eenheidParam) {
      setSelectedId(eenheidParam);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const { data: tree = [], isLoading } = useOrganisatieTree(includeHistorisch);
  const { currentPerson } = useCurrentPerson();
  const { data: ownPlacements = [] } = usePersonOrganisaties(
    currentPerson?.id ?? null,
  );

  // Default-open: pad van root naar elk eigen-organisatie-id van de gebruiker.
  // Met 1900+ nodes is alles dicht onhanteerbaar; je eigen ministerie hoort
  // wel als entrypoint open te staan. We pakken alle actieve placements
  // (functietitel-rollen onder een eenheid) van currentPerson.
  const expandedByDefaultIds = useMemo(() => {
    const eigenIds = new Set(ownPlacements.map((p) => p.organisatie_eenheid_id));
    if (eigenIds.size === 0) return new Set<string>();
    const open = new Set<string>();
    const walk = (nodes: typeof tree, ancestors: string[]): boolean => {
      let touched = false;
      for (const n of nodes) {
        const path = [...ancestors, n.id];
        const hitChild = walk(n.children, path);
        if (eigenIds.has(n.id) || hitChild) {
          // Open alle ancestors plus de matchende node zelf, zodat children
          // van de eigen-org zichtbaar worden zonder dat de eigen-org per
          // se hoeft te worden geklikt.
          for (const aid of path) open.add(aid);
          touched = true;
        }
      }
      return touched;
    };
    walk(tree, []);
    return open;
  }, [tree, ownPlacements]);

  // Filter de boom op zoekterm + bron: een node blijft staan als hijzelf
  // matcht OF een afstammeling matcht. Synthetische groepen worden altijd
  // getoond als ze matchende children hebben (anders wordt de tree-structuur
  // onnavigeerbaar).
  const filteredTree = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    const matchesBron = (bron: string | null | undefined): boolean => {
      if (bronFilter === 'alle') return true;
      if (bronFilter === 'scrape')
        return bron === 'organogram_scrape' || bron === 'fcc_import';
      if (bronFilter === 'tooi') return bron === 'tooi';
      return bron === 'handmatig';
    };
    const matches = (n: (typeof tree)[number]): boolean => {
      // Synthetische groepen: tonen als ze matchende children hebben
      if (n.bron === 'synthetisch') return n.children.some(matches);
      const termMatch =
        !term ||
        n.naam.toLowerCase().includes(term) ||
        (n.afkorting?.toLowerCase().includes(term) ?? false);
      const bronMatch = matchesBron(n.bron);
      const self = termMatch && bronMatch;
      const child = n.children.some(matches);
      return self || child;
    };
    const filter = (nodes: typeof tree): typeof tree =>
      nodes
        .filter(matches)
        .map((n) => ({ ...n, children: filter(n.children) }));
    return filter(tree);
  }, [tree, searchTerm, bronFilter]);
  const createMutation = useCreateOrganisatieEenheid();
  const updateMutation = useUpdateOrganisatieEenheid();
  const deleteMutation = useDeleteOrganisatieEenheid();
  const addPlacementMutation = useAddPersonOrganisatie();
  const { handleSubmit: handlePersonFormSubmit, isPending: isPersonPending } = usePersonFormSubmit(
    () => {
      setShowPersonForm(false);
      setCreatedApiKey(null);
    },
    (person) => {
      if (person.api_key && person.is_agent) {
        setCreatedApiKey(person.api_key);
        setEditPerson(person);
      }
    },
  );

  const handleAdd = (parentId: string | null) => {
    setEditData(null);
    setDefaultParentId(parentId);
    setShowForm(true);
  };

  const handleEdit = () => {
    if (!selectedId) return;
    // Find the selected node in the flat tree
    const findNode = (nodes: typeof tree): OrganisatieEenheid | null => {
      for (const n of nodes) {
        if (n.id === selectedId) return n;
        const found = findNode(n.children);
        if (found) return found;
      }
      return null;
    };
    const node = findNode(tree);
    if (node) {
      setEditData(node);
      setDefaultParentId(null);
      setShowForm(true);
    }
  };

  const handleDelete = () => {
    if (!selectedId) return;
    deleteMutation.mutate(selectedId, {
      onSuccess: () => setSelectedId(null),
    });
  };

  const handleFormSubmit = (data: OrganisatieEenheidCreate | OrganisatieEenheidUpdate) => {
    if (editData) {
      updateMutation.mutate(
        { id: editData.id, data: data as OrganisatieEenheidUpdate },
        { onSuccess: () => setShowForm(false) },
      );
    } else {
      createMutation.mutate(data as OrganisatieEenheidCreate, {
        onSuccess: () => setShowForm(false),
      });
    }
  };

  // Person handlers
  const [defaultIsAgent, setDefaultIsAgent] = useState(false);

  const handleAddPerson = () => {
    setEditPerson(null);
    setDefaultIsAgent(false);
    setShowPersonForm(true);
  };

  const handleAddAgent = () => {
    setEditPerson(null);
    setDefaultIsAgent(true);
    setShowPersonForm(true);
  };

  const handleEditPerson = (person: Person) => {
    setEditPerson(person);
    setShowPersonForm(true);
  };

  const handleDragStartPerson = (e: React.DragEvent, person: Person) => {
    e.dataTransfer.setData('application/person-id', person.id);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDropPerson = (personId: string, targetNodeId: string) => {
    addPlacementMutation.mutate({
      personId,
      data: {
        organisatie_eenheid_id: targetNodeId,
        dienstverband: 'in_dienst',
        start_datum: todayISO(),
      },
    });
  };

  if (isLoading) {
    return <LoadingSpinner className="py-12" />;
  }

  const isEmpty = tree.length === 0;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <p className="text-sm text-text-secondary">
            Beheer de organisatiestructuur: Ministerie, DG, Directie, Afdeling, Team.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            icon={<Plus className="h-4 w-4" />}
            onClick={() => handleAdd(null)}
          >
            <span className="hidden sm:inline">Eenheid toevoegen</span>
          </Button>
        </div>
      </div>

      {isEmpty ? (
        <EmptyState
          icon={<Building2 className="h-16 w-16" />}
          title="Nog geen organisatie-eenheden"
          description="Begin met het opzetten van de organisatiestructuur door een top-niveau eenheid toe te voegen."
          action={
            <Button variant="primary" onClick={() => handleAdd(null)}>
              Eerste eenheid aanmaken
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left panel: Tree */}
          <div className="lg:col-span-1">
            <Card>
              <div className="p-2">
                <div className="relative mb-2">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Zoek organisatie of afkorting..."
                    className="w-full pl-8 pr-8 py-1.5 text-sm rounded border border-gray-200 focus:border-primary-500 focus:outline-none"
                  />
                  {searchTerm && (
                    <button
                      onClick={() => setSearchTerm('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 h-5 w-5 flex items-center justify-center text-text-secondary hover:text-text"
                      title="Wis zoekterm"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
                <div className="flex items-center justify-between gap-2 mb-2 px-1">
                  <label className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={includeHistorisch}
                      onChange={(e) => setIncludeHistorisch(e.target.checked)}
                      className="h-3 w-3"
                    />
                    Historisch
                  </label>
                  <select
                    value={bronFilter}
                    onChange={(e) =>
                      setBronFilter(e.target.value as typeof bronFilter)
                    }
                    className="text-xs rounded border border-gray-200 bg-white px-1 py-0.5"
                    title="Filter op bron"
                  >
                    <option value="alle">Alle bronnen</option>
                    <option value="handmatig">Alleen handmatig</option>
                    <option value="tooi">Alleen TOOI</option>
                    <option value="scrape">Alleen scrape/import</option>
                  </select>
                </div>
                <OrganisatieTree
                  tree={filteredTree}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  onAdd={handleAdd}
                  onDropPerson={handleDropPerson}
                  searchTerm={searchTerm}
                  expandedByDefaultIds={expandedByDefaultIds}
                />
              </div>
            </Card>
          </div>

          {/* Right panel: Detail */}
          <div className="lg:col-span-2">
            {selectedId ? (
              <Card>
                <div className="p-2">
                  <OrganisatieDetail
                    selectedId={selectedId}
                    onEdit={handleEdit}
                    onDelete={handleDelete}
                    onAddChild={() => handleAdd(selectedId)}
                    onAddPerson={handleAddPerson}
                    onAddAgent={handleAddAgent}
                    onEditPerson={handleEditPerson}
                    onDragStartPerson={handleDragStartPerson}
                    onDropPerson={handleDropPerson}
                  />
                </div>
              </Card>
            ) : (
              <Card>
                <div className="text-center py-12 text-text-secondary">
                  <Building2 className="h-12 w-12 mx-auto mb-3 opacity-30" />
                  <p className="text-sm">Selecteer een eenheid in de boomstructuur.</p>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* Create/Edit org form */}
      <OrganisatieForm
        open={showForm}
        onClose={() => setShowForm(false)}
        onSubmit={handleFormSubmit}
        isLoading={createMutation.isPending || updateMutation.isPending}
        editData={editData}
        defaultParentId={defaultParentId}
      />

      {/* Create/Edit person form */}
      <PersonEditForm
        open={showPersonForm}
        onClose={() => {
          setShowPersonForm(false);
          setCreatedApiKey(null);
        }}
        onSubmit={handlePersonFormSubmit}
        isLoading={isPersonPending}
        editData={editPerson}
        defaultIsAgent={defaultIsAgent}
        defaultOrgEenheidId={selectedId || undefined}
        createdApiKey={createdApiKey}
      />
    </div>
  );
}
