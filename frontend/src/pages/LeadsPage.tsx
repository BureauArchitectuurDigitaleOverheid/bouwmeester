import { useCallback, useRef, useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { Modal } from '@/components/common/Modal';
import { ViewToggle } from '@/components/common/ViewToggle';
import type { ViewToggleOption } from '@/components/common/ViewToggle';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { Icon } from '@/components/nldd/Icon';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { eventValue, useNlddEvent } from '@/components/nldd/events';
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
  { value: 'inbox', label: 'Inbox', icon: <Icon name="inbox" size="sm" /> },
  { value: 'kanban', label: 'Bord', icon: <Icon name="columns-3" size="sm" /> },
  { value: 'list', label: 'Lijst', icon: <Icon name="square-grid-2x2" size="sm" /> },
  { value: 'timeline', label: 'Tijdlijn', icon: <Icon name="clock" size="sm" /> },
  { value: 'graph', label: 'Netwerk', icon: <Icon name="git-fork" size="sm" /> },
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

/**
 * Controlled `nldd-text-field` for the new-initiatief naam field, wired
 * directly rather than through the shared `Input` component: `Input`'s
 * `onChange` is not forwarded to its underlying nldd element (see the
 * conversion report), so it silently no-ops on every keystroke there.
 */
function InitiatiefNaamField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLElement & { focus?: () => void }>(null);
  useNlddEvent(ref, 'input', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  useEffect(() => {
    ref.current?.focus?.();
  }, []);
  return (
    <nldd-text-field
      ref={ref}
      value={value}
      placeholder="Naam van het initiatief"
      required
      accessible-label="Naam"
    />
  );
}

/**
 * Link to the initiatief's public page. `nldd-link` has no icon-only mode
 * (it is always a self-describing, visibly labelled link, unlike
 * nldd-icon-button) and no arbitrary color attribute, so the "this is live"
 * emphasis that the old emerald icon carried is dropped rather than faked.
 */
function PublicPageLink({ slug }: { slug: string }) {
  return (
    <nldd-link
      href={`/c/${slug}`}
      target="_blank"
      size="xs"
      start-icon="globe"
      text={`/c/${slug}`}
    />
  );
}

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
    <nldd-container gap="16">
      {/* Page header */}
      <nldd-toolbar label="Leadacties">
        {/* `min-width` is what makes a toolbar item fluid, per its own docs:
            "Setting it (or width or max-width) makes the item fluid so it grows
            to fill the available space." Without it the item measures its
            content, a wrap container inside measures its parent, and the two
            collapse to zero width — the pills then stacked one per line and the
            row grew from 64 to 198 pixels tall. */}
        <nldd-toolbar-item slot="start" priority={1} min-width="320px">
          {/* Initiative pills: per-initiatief color is an arbitrary hex on
              the record, not one of nldd-tag's closed color names, so this
              stays a styled button rather than a guessed tag color (same
              call as the initiatief chips in LeadListView/LeadDetailPanel). */}
          <nldd-container layout="wrap" gap="6">
            {initiatieven?.map((ini) => (
              <button
                key={ini.id}
                onClick={() => setSelectedInitiatiefId(ini.id)}
                style={{
                  borderRadius: '9999px',
                  padding: '4px 12px',
                  fontSize: '12px',
                  fontWeight: 500,
                  color: 'white',
                  backgroundColor: ini.kleur || '#6B7280',
                  opacity: selectedInitiatiefId === ini.id ? 1 : 0.4,
                  boxShadow:
                    selectedInitiatiefId === ini.id
                      ? '0 0 0 2px white, 0 0 0 4px var(--primitives-color-neutral-400), 0 1px 2px rgba(0,0,0,0.1)'
                      : 'none',
                }}
              >
                {ini.naam}
              </button>
            ))}
            <NlddIconButton
              icon="plus"
              accessibleLabel="Nieuw initiatief"
              variant="neutral-transparent"
              size="sm"
              onClick={() => setShowCreateInitiatief(true)}
            />
            {selectedInitiatiefId && (
              <NlddIconButton
                icon="gear"
                accessibleLabel="Initiatief beheren"
                variant="neutral-transparent"
                size="sm"
                onClick={() => setEditInitiatiefId(selectedInitiatiefId)}
              />
            )}
            {(() => {
              if (!selectedInitiatiefId) return null;
              const sel = initiatieven?.find((i) => i.id === selectedInitiatiefId);
              if (!sel?.public_page_enabled || !sel.slug) return null;
              return (
                <PublicPageLink slug={sel.slug} />
              );
            })()}
          </nldd-container>
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
            <span className="hidden sm:inline">Nieuwe lead</span>
          </Button>
          <nldd-menu-item slot="overflow" text="Nieuwe lead" icon="plus"></nldd-menu-item>
        </nldd-toolbar-item>
      </nldd-toolbar>

      {/* Shared filter bar */}
      <nldd-container layout="wrap" gap="12" vertical-alignment="center">
        {/* Search */}
        <nldd-container width="fit-content" min-width="224px">
          <LeadsSearchField value={searchInput} onChange={setSearchInput} />
        </nldd-container>

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
          <nldd-container layout="row" gap="4" width="fit-content" min-width="176px">
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

        {/* Clear filters */}
        {hasActiveFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            Filters wissen
          </Button>
        )}
      </nldd-container>

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
          <nldd-container gap="16">
            <nldd-form-field label="Naam">
              <InitiatiefNaamField
                value={createForm.naam}
                onChange={(v) => setCreateForm({ ...createForm, naam: v })}
              />
            </nldd-form-field>
            <RichTextFormField
              label="Beschrijving"
              value={createForm.beschrijving || ''}
              onChange={(value) => setCreateForm({ ...createForm, beschrijving: value })}
              rows={3}
              placeholder="Korte beschrijving..."
            />
            <nldd-form-field label="Kleur">
              {/* Free-form hex swatch picker: no nldd primitive renders a circle
                  that IS an arbitrary color (nldd-radio-button is a fixed dot
                  glyph), same as InitiatiefDetailModal's EditForm. */}
              <nldd-container layout="wrap" gap="8">
                {INITIATIEF_COLORS.map((color) => (
                  <button
                    key={color}
                    type="button"
                    onClick={() => setCreateForm({ ...createForm, kleur: color })}
                    style={{
                      height: '32px',
                      width: '32px',
                      borderRadius: '9999px',
                      border: `2px solid ${createForm.kleur === color ? 'var(--primitives-color-accent-75)' : 'transparent'}`,
                      transform: createForm.kleur === color ? 'scale(1.1)' : 'scale(1)',
                      backgroundColor: color,
                    }}
                  />
                ))}
              </nldd-container>
            </nldd-form-field>
          </nldd-container>
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
    </nldd-container>
  );
}
