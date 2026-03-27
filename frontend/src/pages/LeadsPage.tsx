import { useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Plus, Columns3, LayoutGrid, GitFork, Clock, Search } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { ViewToggle } from '@/components/common/ViewToggle';
import type { ViewToggleOption } from '@/components/common/ViewToggle';
import { useDebounce } from '@/hooks/useDebounce';
import { LeadKanbanBoard } from '@/components/leads/LeadKanbanBoard';
import { LeadListView } from '@/components/leads/LeadListView';
import { LeadGraphView } from '@/components/leads/LeadGraphView';
import { LeadTimelineView } from '@/components/leads/LeadTimelineView';
import { LeadIntakeDialog } from '@/components/leads/LeadIntakeDialog';

type LeadViewMode = 'kanban' | 'list' | 'graph' | 'timeline';

const VIEW_OPTIONS: ViewToggleOption<LeadViewMode>[] = [
  { value: 'kanban', label: 'Kanban', icon: <Columns3 className="h-3.5 w-3.5" /> },
  { value: 'list', label: 'Lijst', icon: <LayoutGrid className="h-3.5 w-3.5" /> },
  { value: 'timeline', label: 'Tijdlijn', icon: <Clock className="h-3.5 w-3.5" /> },
  { value: 'graph', label: 'Netwerk', icon: <GitFork className="h-3.5 w-3.5" /> },
];

export function LeadsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const viewParam = searchParams.get('view');
  const viewMode: LeadViewMode =
    viewParam === 'list'
      ? 'list'
      : viewParam === 'graph'
        ? 'graph'
        : viewParam === 'timeline'
          ? 'timeline'
          : 'kanban';

  const [showIntake, setShowIntake] = useState(false);
  const [searchInput, setSearchInput] = useState('');
  const searchQuery = useDebounce(searchInput, 200);

  const setViewMode = useCallback(
    (mode: LeadViewMode) => {
      setSearchParams((prev) => {
        if (mode === 'kanban') {
          prev.delete('view');
        } else {
          prev.set('view', mode);
        }
        return prev;
      }, { replace: true });
    },
    [setSearchParams],
  );

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <p className="text-sm text-text-secondary">
            Beheer en volg leads door de pipeline.
          </p>
        </div>
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <div className="relative w-full sm:w-56">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-secondary" />
            <Input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Zoek in leads..."
              className="pl-9"
            />
          </div>
          <ViewToggle value={viewMode} onChange={setViewMode} options={VIEW_OPTIONS} />
          <Button
            icon={<Plus className="h-4 w-4" />}
            onClick={() => setShowIntake(true)}
          >
            <span className="hidden sm:inline">Nieuwe lead</span>
          </Button>
        </div>
      </div>

      {/* View content */}
      {viewMode === 'kanban' ? (
        <LeadKanbanBoard searchQuery={searchQuery} />
      ) : viewMode === 'list' ? (
        <LeadListView searchQuery={searchQuery} />
      ) : viewMode === 'timeline' ? (
        <LeadTimelineView />
      ) : viewMode === 'graph' ? (
        <LeadGraphView />
      ) : null}

      <LeadIntakeDialog open={showIntake} onClose={() => setShowIntake(false)} />
    </div>
  );
}
