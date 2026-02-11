import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus, Building2 } from 'lucide-react';
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
import { useAddPersonOrganisatie } from '@/hooks/usePeople';
import { usePersonFormSubmit } from '@/hooks/usePersonFormSubmit';
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

  // Sync ?eenheid= param on arrival, then clear it
  useEffect(() => {
    const eenheidParam = searchParams.get('eenheid');
    if (eenheidParam) {
      setSelectedId(eenheidParam);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const { data: tree = [], isLoading } = useOrganisatieTree();
  const createMutation = useCreateOrganisatieEenheid();
  const updateMutation = useUpdateOrganisatieEenheid();
  const deleteMutation = useDeleteOrganisatieEenheid();
  const addPlacementMutation = useAddPersonOrganisatie();
  const { handleSubmit: handlePersonFormSubmit, isPending: isPersonPending } = usePersonFormSubmit(
    () => setShowPersonForm(false),
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
    addPlacementMutation.mutate(
      {
        personId,
        data: {
          organisatie_eenheid_id: targetNodeId,
          dienstverband: 'in_dienst',
          start_datum: todayISO(),
        },
      },
      {
        onError: (error) => {
          console.error('Plaatsing mislukt:', error);
        },
      },
    );
  };

  if (isLoading) {
    return <LoadingSpinner className="py-12" />;
  }

  const isEmpty = tree.length === 0;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-text-secondary">
            Beheer de organisatiestructuur: Ministerie, DG, Directie, Afdeling, Team.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            icon={<Plus className="h-4 w-4" />}
            onClick={() => handleAdd(null)}
          >
            Eenheid toevoegen
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
              <div className="p-1">
                <OrganisatieTree
                  tree={tree}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  onAdd={handleAdd}
                  onDropPerson={handleDropPerson}
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
        onClose={() => setShowPersonForm(false)}
        onSubmit={handlePersonFormSubmit}
        isLoading={isPersonPending}
        editData={editPerson}
        defaultIsAgent={defaultIsAgent}
        defaultOrgEenheidId={selectedId || undefined}
      />
    </div>
  );
}
