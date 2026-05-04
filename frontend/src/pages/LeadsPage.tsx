import { useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus, Columns3, LayoutGrid, GitFork, Clock, Search, X, Settings, Inbox } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { Modal } from '@/components/common/Modal';
import { ViewToggle } from '@/components/common/ViewToggle';
import type { ViewToggleOption } from '@/components/common/ViewToggle';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { useDebounce } from '@/hooks/useDebounce';
import { usePeople } from '@/hooks/usePeople';
import { useInitiatieven, useCreateInitiatief } from '@/hooks/useInitiatieven';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { InitiatiefDetailModal } from '@/components/initiatieven/InitiatiefDetailModal';
import { LeadKanbanBoard } from '@/components/leads/LeadKanbanBoard';
import { LeadListView } from '@/components/leads/LeadListView';
import { LeadGraphView } from '@/components/leads/LeadGraphView';
import { LeadTimelineView } from '@/components/leads/LeadTimelineView';
import { LeadInboxView } from '@/components/leads/LeadInboxView';
import { LeadIntakeDialog } from '@/components/leads/LeadIntakeDialog';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import {
  LeadStage,
  LEAD_STAGE_LABELS,
  INITIATIEF_COLORS,
} from '@/types';
import type { InitiatiefCreate } from '@/types';
import { useGlobalFileDropContext } from '@/hooks/useGlobalFileDropContext';

type LeadViewMode = 'inbox' | 'kanban' | 'list' | 'graph' | 'timeline';

const VIEW_OPTIONS: ViewToggleOption<LeadViewMode>[] = [
  { value: 'inbox', label: 'Inbox', icon: <Inbox className="h-3.5 w-3.5" /> },
  { value: 'kanban', label: 'Bord', icon: <Columns3 className="h-3.5 w-3.5" /> },
  { value: 'list', label: 'Lijst', icon: <LayoutGrid className="h-3.5 w-3.5" /> },
  { value: 'timeline', label: 'Tijdlijn', icon: <Clock className="h-3.5 w-3.5" /> },
  { value: 'graph', label: 'Netwerk', icon: <GitFork className="h-3.5 w-3.5" /> },
];

const NEXT_ACTION_OPTIONS: SelectOption[] = [
  { value: '', label: 'Alle acties' },
  { value: 'overdue', label: 'Achterstallig' },
  { value: 'today', label: 'Vandaag' },
  { value: 'this_week', label: 'Deze week' },
];

const STAGE_OPTIONS: SelectOption[] = [
  { value: '', label: 'Alle fases' },
  ...Object.values(LeadStage).map((s) => ({
    value: s,
    label: LEAD_STAGE_LABELS[s],
  })),
];

export function LeadsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const viewParam = searchParams.get('view');
  const viewMode: LeadViewMode =
    viewParam === 'kanban'
      ? 'kanban'
      : viewParam === 'list'
        ? 'list'
        : viewParam === 'graph'
          ? 'graph'
          : viewParam === 'timeline'
            ? 'timeline'
            : 'inbox';

  const [showIntake, setShowIntake] = useState(false);
  const { subscribe } = useGlobalFileDropContext();
  const [droppedFiles, setDroppedFiles] = useState<File[]>([]);

  // Subscribe to global file drops while this page is mounted
  useEffect(() => {
    return subscribe((files) => {
      setDroppedFiles(files);
      setShowIntake(true);
    });
  }, [subscribe]);
  const [showCreateInitiatief, setShowCreateInitiatief] = useState(false);
  const [editInitiatiefId, setEditInitiatiefId] = useState<string | null>(null);

  // Search
  const [searchInput, setSearchInput] = useState('');
  const searchQuery = useDebounce(searchInput, 200);

  // Shared filters
  const [filterAssignee, setFilterAssignee] = useState('');
  const [filterTag, setFilterTag] = useState('');
  const [nextActionFilter, setNextActionFilter] = useState('');
  const [filterStage, setFilterStage] = useState('');

  // Initiative toggle
  const { data: initiatieven } = useInitiatieven();
  const createInitiatief = useCreateInitiatief();
  const selectedInitiatiefParam = searchParams.get('initiatief') ?? '';
  const [selectedInitiatiefId, setSelectedInitiatiefIdState] = useState(selectedInitiatiefParam);

  // Create initiative form
  const [createForm, setCreateForm] = useState<InitiatiefCreate>({
    naam: '',
    beschrijving: '',
    kleur: INITIATIEF_COLORS[0],
  });

  // People for assignee filter
  const { data: people } = usePeople();
  const { currentPerson } = useCurrentPerson();

  const setSelectedInitiatiefId = useCallback(
    (id: string) => {
      setSelectedInitiatiefIdState(id);
      setSearchParams((prev) => {
        if (id) {
          prev.set('initiatief', id);
        } else {
          prev.delete('initiatief');
        }
        return prev;
      }, { replace: true });
    },
    [setSearchParams],
  );

  // Auto-select first initiative when data loads
  useEffect(() => {
    if (initiatieven?.length && !initiatieven.find((i) => i.id === selectedInitiatiefId)) {
      setSelectedInitiatiefId(initiatieven[0].id);
    }
  }, [initiatieven, selectedInitiatiefId, setSelectedInitiatiefId]);

  const setViewMode = useCallback(
    (mode: LeadViewMode) => {
      setSearchParams((prev) => {
        if (mode === 'inbox') {
          prev.delete('view');
        } else {
          prev.set('view', mode);
        }
        return prev;
      }, { replace: true });
    },
    [setSearchParams],
  );

  const handleCreateInitiatief = async () => {
    if (!createForm.naam.trim()) return;
    const result = await createInitiatief.mutateAsync(createForm);
    setSelectedInitiatiefId(result.id);
    setShowCreateInitiatief(false);
    setCreateForm({ naam: '', beschrijving: '', kleur: INITIATIEF_COLORS[0] });
  };

  // Filters applicable per view: inbox uses only search; kanban+list support all; timeline lacks tag/next_action; graph only has stage
  const supportsAssignee = viewMode !== 'graph' && viewMode !== 'inbox';
  const supportsTag = viewMode === 'kanban' || viewMode === 'list';
  const supportsNextAction = viewMode === 'kanban' || viewMode === 'list';
  const supportsStage = viewMode !== 'inbox';

  const hasActiveFilters = filterAssignee || filterTag || nextActionFilter || filterStage;

  const clearFilters = () => {
    setFilterAssignee('');
    setFilterTag('');
    setNextActionFilter('');
    setFilterStage('');
  };

  return (
    <div className="space-y-4">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* Initiative pills */}
          {initiatieven?.map((ini) => (
            <button
              key={ini.id}
              onClick={() => setSelectedInitiatiefId(ini.id)}
              className={`rounded-full px-3 py-1 text-xs font-medium text-white transition-all ${
                selectedInitiatiefId === ini.id
                  ? 'ring-2 ring-offset-2 ring-gray-400 shadow-sm'
                  : 'opacity-40 hover:opacity-70'
              }`}
              style={{ backgroundColor: ini.kleur || '#6B7280' }}
            >
              {ini.naam}
            </button>
          ))}
          <button
            onClick={() => setShowCreateInitiatief(true)}
            className="rounded-full w-7 h-7 flex items-center justify-center border border-dashed border-gray-300 text-text-secondary hover:border-gray-400 hover:text-text transition-colors"
            title="Nieuw initiatief"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          {selectedInitiatiefId && (
            <button
              onClick={() => setEditInitiatiefId(selectedInitiatiefId)}
              className="rounded-full w-7 h-7 flex items-center justify-center text-text-secondary hover:text-text hover:bg-gray-100 transition-colors"
              title="Initiatief beheren"
            >
              <Settings className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <ViewToggle value={viewMode} onChange={setViewMode} options={VIEW_OPTIONS} />
          <Button
            icon={<Plus className="h-4 w-4" />}
            onClick={() => setShowIntake(true)}
          >
            <span className="hidden sm:inline">Nieuwe lead</span>
          </Button>
        </div>
      </div>

      {/* Shared filter bar */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
        {/* Search */}
        <div className="relative w-full sm:w-56">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Zoek in leads..."
            className="pl-9"
          />
        </div>

        {/* Assignee */}
        {supportsAssignee && (
          <div className="w-full sm:w-48">
            <CreatableSelect
              value={filterAssignee}
              onChange={setFilterAssignee}
              options={[
                { value: '', label: 'Alle personen' },
                ...(currentPerson
                  ? [{ value: currentPerson.id, label: `Mijn leads (${currentPerson.naam})` }]
                  : []),
                ...(people
                  ?.filter((p) => p.is_active && p.id !== currentPerson?.id)
                  .map((p) => ({ value: p.id, label: p.naam, description: p.functie ?? undefined })) ?? []),
              ]}
              placeholder="Alle personen"
              onClear={filterAssignee ? () => setFilterAssignee('') : undefined}
            />
          </div>
        )}

        {/* Tag */}
        {supportsTag && (
          <div className="relative w-full sm:w-44">
            <Input
              value={filterTag}
              onChange={(e) => setFilterTag(e.target.value)}
              placeholder="Filter op tag..."
            />
            {filterTag && (
              <button
                onClick={() => setFilterTag('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-text-secondary hover:text-text"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        )}

        {/* Next action */}
        {supportsNextAction && (
          <div className="w-full sm:w-40">
            <CreatableSelect
              value={nextActionFilter}
              onChange={setNextActionFilter}
              options={NEXT_ACTION_OPTIONS}
              placeholder="Alle acties"
              searchable={false}
              onClear={nextActionFilter ? () => setNextActionFilter('') : undefined}
            />
          </div>
        )}

        {/* Stage */}
        {supportsStage && (
          <div className="w-full sm:w-40">
            <CreatableSelect
              value={filterStage}
              onChange={setFilterStage}
              options={STAGE_OPTIONS}
              placeholder="Alle fases"
              searchable={false}
              onClear={filterStage ? () => setFilterStage('') : undefined}
            />
          </div>
        )}

        {/* Clear filters */}
        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="text-sm text-text-secondary hover:text-text transition-colors whitespace-nowrap"
          >
            Filters wissen
          </button>
        )}
      </div>

      {/* View content */}
      {viewMode === 'inbox' ? (
        <LeadInboxView
          searchQuery={searchQuery}
          initiatiefId={selectedInitiatiefId}
        />
      ) : viewMode === 'kanban' ? (
        <LeadKanbanBoard
          searchQuery={searchQuery}
          initiatiefId={selectedInitiatiefId}
          assigneeId={filterAssignee}
          tag={filterTag}
          nextActionFilter={nextActionFilter}
          stageFilter={filterStage}
        />
      ) : viewMode === 'list' ? (
        <LeadListView
          searchQuery={searchQuery}
          initiatiefId={selectedInitiatiefId}
          assigneeId={filterAssignee}
          tag={filterTag}
          nextActionFilter={nextActionFilter}
          stageFilter={filterStage}
        />
      ) : viewMode === 'timeline' ? (
        <LeadTimelineView
          searchQuery={searchQuery}
          initiatiefId={selectedInitiatiefId}
          assigneeId={filterAssignee}
          stageFilter={filterStage}
        />
      ) : viewMode === 'graph' ? (
        <LeadGraphView
          searchQuery={searchQuery}
          initiatiefId={selectedInitiatiefId}
          stageFilter={filterStage}
        />
      ) : null}

      <LeadIntakeDialog
        open={showIntake}
        onClose={() => { setShowIntake(false); setDroppedFiles([]); }}
        defaultInitiatiefId={selectedInitiatiefId}
        initialFiles={droppedFiles.length > 0 ? droppedFiles : undefined}
      />

      {/* Create initiatief modal */}
      {showCreateInitiatief && (
        <Modal
          open
          onClose={() => setShowCreateInitiatief(false)}
          title="Nieuw initiatief"
          size="sm"
          footer={
            <>
              <Button variant="secondary" onClick={() => setShowCreateInitiatief(false)} disabled={createInitiatief.isPending}>
                Annuleren
              </Button>
              <Button
                onClick={handleCreateInitiatief}
                loading={createInitiatief.isPending}
                disabled={!createForm.naam.trim()}
              >
                Aanmaken
              </Button>
            </>
          }
        >
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-text">
                Naam <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={createForm.naam}
                onChange={(e) => setCreateForm({ ...createForm, naam: e.target.value })}
                className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
                placeholder="Naam van het initiatief"
                autoFocus
              />
            </div>
            <RichTextFormField
              label="Beschrijving"
              value={createForm.beschrijving || ''}
              onChange={(value) => setCreateForm({ ...createForm, beschrijving: value })}
              rows={3}
              placeholder="Korte beschrijving..."
            />
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-text">Kleur</label>
              <div className="flex gap-2 flex-wrap">
                {INITIATIEF_COLORS.map((color) => (
                  <button
                    key={color}
                    type="button"
                    onClick={() => setCreateForm({ ...createForm, kleur: color })}
                    className={`h-8 w-8 rounded-full border-2 transition-all ${
                      createForm.kleur === color
                        ? 'border-primary-500 scale-110'
                        : 'border-transparent hover:scale-105'
                    }`}
                    style={{ backgroundColor: color }}
                  />
                ))}
              </div>
            </div>
          </div>
        </Modal>
      )}

      {/* Initiatief detail/edit modal */}
      {editInitiatiefId && (
        <InitiatiefDetailModal
          initiatiefId={editInitiatiefId}
          open={!!editInitiatiefId}
          onClose={() => setEditInitiatiefId(null)}
        />
      )}
    </div>
  );
}
