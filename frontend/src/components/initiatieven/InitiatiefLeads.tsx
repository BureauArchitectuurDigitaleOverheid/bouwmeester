import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { ViewToggle } from '@/components/common/ViewToggle';
import type { ViewToggleOption } from '@/components/common/ViewToggle';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { Icon } from '@/components/nldd/Icon';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { eventValue, useNlddEvent } from '@/components/nldd/events';
import { useDebounce } from '@/hooks/useDebounce';
import { usePeople } from '@/hooks/usePeople';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { LeadKanbanBoard } from '@/components/leads/LeadKanbanBoard';
import { LeadListView } from '@/components/leads/LeadListView';
import { LeadGraphView } from '@/components/leads/LeadGraphView';
import { LeadTimelineView } from '@/components/leads/LeadTimelineView';
import { LeadInboxView } from '@/components/leads/LeadInboxView';
import { LeadIntakeDialog } from '@/components/leads/LeadIntakeDialog';
import { LeadStage, LEAD_STAGE_LABELS } from '@/types';
import { useGlobalFileDropContext } from '@/hooks/useGlobalFileDropContext';

type LeadViewMode = 'inbox' | 'kanban' | 'list' | 'graph' | 'timeline';

const VIEW_OPTIONS: ViewToggleOption<LeadViewMode>[] = [
  { value: 'inbox', label: 'Inbox', icon: <Icon name="inbox" size="sm" /> },
  { value: 'kanban', label: 'Bord', icon: <Icon name="columns-3" size="sm" /> },
  { value: 'list', label: 'Lijst', icon: <Icon name="square-grid-2x2" size="sm" /> },
  { value: 'timeline', label: 'Tijdlijn', icon: <Icon name="clock" size="sm" /> },
  { value: 'graph', label: 'Netwerk', icon: <Icon name="git-fork" size="sm" /> },
];

const VIEW_MODES: readonly LeadViewMode[] = ['inbox', 'kanban', 'list', 'graph', 'timeline'];

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

/** The leads search field: `nldd-search-field` with its `input` event bridged to React. */
function LeadsSearchField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  return (
    <nldd-search-field
      ref={ref}
      value={value}
      placeholder="Zoek in leads..."
      accessible-label="Zoek in leads"
    />
  );
}

/**
 * The "Leads" tab of an initiatief: the funnel in five views, with the
 * filters that apply to the current one. This was the leads page, minus the
 * row of initiatief pills: the initiatief is fixed by the page it sits on.
 */
export function InitiatiefLeads({ initiatiefId }: { initiatiefId: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const viewParam = searchParams.get('view') as LeadViewMode | null;
  const viewMode: LeadViewMode = viewParam && VIEW_MODES.includes(viewParam) ? viewParam : 'inbox';

  const [showIntake, setShowIntake] = useState(false);
  const { subscribe } = useGlobalFileDropContext();
  const [droppedFiles, setDroppedFiles] = useState<File[]>([]);

  // Subscribe to global file drops while this tab is mounted
  useEffect(() => {
    return subscribe((files) => {
      setDroppedFiles(files);
      setShowIntake(true);
    });
  }, [subscribe]);

  // Search
  const [searchInput, setSearchInput] = useState('');
  const searchQuery = useDebounce(searchInput, 200);

  // Shared filters
  const [filterAssignee, setFilterAssignee] = useState('');
  const [filterTag, setFilterTag] = useState('');
  const [nextActionFilter, setNextActionFilter] = useState('');
  const [filterStage, setFilterStage] = useState('');

  // People for assignee filter
  const { data: people } = usePeople();
  const { currentPerson } = useCurrentPerson();

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
    <nldd-container gap="16">
      <nldd-toolbar label="Leadacties">
        {/* The search field is the fluid item: `min-width` is what makes a
            toolbar item grow into the room the others leave. */}
        <nldd-toolbar-item slot="start" priority={1} min-width="224px">
          <LeadsSearchField value={searchInput} onChange={setSearchInput} />
        </nldd-toolbar-item>
        <nldd-toolbar-item slot="end" priority={3}>
          {/* A view switcher, not a single action: the toolbar pattern gives
              those a high priority so they never collapse into the menu
              (higher priority survives longer — a lower number overflows
              first). */}
          <ViewToggle value={viewMode} onChange={setViewMode} options={VIEW_OPTIONS} />
        </nldd-toolbar-item>
        <nldd-toolbar-item slot="end" priority={2}>
          <Button icon="plus" onClick={() => setShowIntake(true)}>
            <span className="hidden-below-sm">Nieuwe lead</span>
          </Button>
          <nldd-menu-item slot="overflow" text="Nieuwe lead" icon="plus"></nldd-menu-item>
        </nldd-toolbar-item>
      </nldd-toolbar>

      {(supportsAssignee || supportsTag || supportsNextAction || supportsStage) && (
        <nldd-container layout="wrap" gap="12" vertical-alignment="center">
          {/* Assignee */}
          {supportsAssignee && (
            <nldd-container width="fit-content" min-width="192px">
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
            </nldd-container>
          )}

          {/* Tag */}
          {supportsTag && (
            <nldd-container layout="row" gap="4" min-width="176px">
              <nldd-container width="full">
                <Input
                  value={filterTag}
                  onChange={(e) => setFilterTag(e.target.value)}
                  placeholder="Filter op tag..."
                />
              </nldd-container>
              {filterTag && (
                <NlddIconButton
                  icon="close"
                  accessibleLabel="Tag-filter wissen"
                  variant="neutral-transparent"
                  size="sm"
                  onClick={() => setFilterTag('')}
                />
              )}
            </nldd-container>
          )}

          {/* Next action */}
          {supportsNextAction && (
            <nldd-container width="fit-content" min-width="160px">
              <CreatableSelect
                value={nextActionFilter}
                onChange={setNextActionFilter}
                options={NEXT_ACTION_OPTIONS}
                placeholder="Alle acties"
                searchable={false}
                onClear={nextActionFilter ? () => setNextActionFilter('') : undefined}
              />
            </nldd-container>
          )}

          {/* Stage */}
          {supportsStage && (
            <nldd-container width="fit-content" min-width="160px">
              <CreatableSelect
                value={filterStage}
                onChange={setFilterStage}
                options={STAGE_OPTIONS}
                placeholder="Alle fases"
                searchable={false}
                onClear={filterStage ? () => setFilterStage('') : undefined}
              />
            </nldd-container>
          )}

          {hasActiveFilters && (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              Filters wissen
            </Button>
          )}
        </nldd-container>
      )}

      {viewMode === 'inbox' ? (
        <LeadInboxView searchQuery={searchQuery} initiatiefId={initiatiefId} />
      ) : viewMode === 'kanban' ? (
        <LeadKanbanBoard
          searchQuery={searchQuery}
          initiatiefId={initiatiefId}
          assigneeId={filterAssignee}
          tag={filterTag}
          nextActionFilter={nextActionFilter}
          stageFilter={filterStage}
        />
      ) : viewMode === 'list' ? (
        <LeadListView
          searchQuery={searchQuery}
          initiatiefId={initiatiefId}
          assigneeId={filterAssignee}
          tag={filterTag}
          nextActionFilter={nextActionFilter}
          stageFilter={filterStage}
        />
      ) : viewMode === 'timeline' ? (
        <LeadTimelineView
          searchQuery={searchQuery}
          initiatiefId={initiatiefId}
          assigneeId={filterAssignee}
          stageFilter={filterStage}
        />
      ) : (
        <LeadGraphView searchQuery={searchQuery} initiatiefId={initiatiefId} stageFilter={filterStage} />
      )}

      <LeadIntakeDialog
        open={showIntake}
        onClose={() => { setShowIntake(false); setDroppedFiles([]); }}
        defaultInitiatiefId={initiatiefId}
        initialFiles={droppedFiles.length > 0 ? droppedFiles : undefined}
      />
    </nldd-container>
  );
}
