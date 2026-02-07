import { useState } from 'react';
import { Plus, LayoutGrid, GitFork } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/common/Button';
import { NodeList } from '@/components/nodes/NodeList';
import { NodeCreateForm } from '@/components/nodes/NodeCreateForm';
import { CorpusGraph } from '@/components/graph/CorpusGraph';

type ViewMode = 'list' | 'graph';

export function CorpusPage() {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('list');

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-text-secondary">
            Bekijk en beheer alle beleidsdocumenten, dossiers en instrumenten.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* View mode toggle */}
          <div className="flex items-center bg-gray-100 rounded-xl p-0.5">
            <button
              onClick={() => setViewMode('list')}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-150',
                viewMode === 'list'
                  ? 'bg-white text-text shadow-sm'
                  : 'text-text-secondary hover:text-text',
              )}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              Lijst
            </button>
            <button
              onClick={() => setViewMode('graph')}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-150',
                viewMode === 'graph'
                  ? 'bg-white text-text shadow-sm'
                  : 'text-text-secondary hover:text-text',
              )}
            >
              <GitFork className="h-3.5 w-3.5" />
              Grafiek
            </button>
          </div>

          <Button
            icon={<Plus className="h-4 w-4" />}
            onClick={() => setShowCreateForm(true)}
          >
            Nieuwe node
          </Button>
        </div>
      </div>

      {/* View content */}
      {viewMode === 'list' ? <NodeList /> : <CorpusGraph />}

      {/* Create form modal */}
      <NodeCreateForm
        open={showCreateForm}
        onClose={() => setShowCreateForm(false)}
      />
    </div>
  );
}
