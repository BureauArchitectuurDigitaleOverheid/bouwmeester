import { useState } from 'react';
import { clsx } from 'clsx';
import { ArrowLeft, Pencil, Trash2, Calendar, Link as LinkIcon, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { PersonCardExpandable } from '@/components/people/PersonCardExpandable';
import { EdgeList } from './EdgeList';
import { TaskView } from '@/components/tasks/TaskView';
import { useNode, useNodeNeighbors, useNodeStakeholders, useDeleteNode } from '@/hooks/useNodes';
import { useTasks } from '@/hooks/useTasks';
import { NODE_TYPE_COLORS, STAKEHOLDER_ROL_LABELS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';

type TabId = 'overview' | 'connections' | 'stakeholders' | 'tasks' | 'activity';

const tabs: { id: TabId; label: string }[] = [
  { id: 'overview', label: 'Overzicht' },
  { id: 'connections', label: 'Verbindingen' },
  { id: 'stakeholders', label: 'Betrokkenen' },
  { id: 'tasks', label: 'Taken' },
  { id: 'activity', label: 'Activiteit' },
];

interface NodeDetailProps {
  nodeId: string;
}

export function NodeDetail({ nodeId }: NodeDetailProps) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const { data: node, isLoading, error } = useNode(nodeId);
  const { data: neighbors } = useNodeNeighbors(nodeId);
  const { data: nodeTasks } = useTasks({ node_id: nodeId });
  const { data: stakeholders } = useNodeStakeholders(nodeId);
  const deleteNode = useDeleteNode();
  const { nodeLabel, nodeAltLabel } = useVocabulary();

  if (isLoading) {
    return <LoadingSpinner className="py-16" />;
  }

  if (error || !node) {
    return (
      <EmptyState
        title="Node niet gevonden"
        description="De gevraagde node bestaat niet of is verwijderd."
        action={
          <Button variant="secondary" onClick={() => navigate('/corpus')}>
            Terug naar corpus
          </Button>
        }
      />
    );
  }

  const color = NODE_TYPE_COLORS[node.node_type];

  const handleDelete = async () => {
    if (window.confirm('Weet je zeker dat je deze node wilt verwijderen?')) {
      await deleteNode.mutateAsync(node.id);
      navigate('/corpus');
    }
  };

  return (
    <div className="space-y-6">
      {/* Back button */}
      <button
        onClick={() => navigate('/corpus')}
        className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Terug naar corpus
      </button>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Badge variant={color as 'blue'} dot title={nodeAltLabel(node.node_type)}>
              {nodeLabel(node.node_type)}
            </Badge>
            {node.status && <Badge variant="gray">{node.status}</Badge>}
          </div>
          <h1 className="text-2xl font-bold text-text">{node.title}</h1>
          <div className="flex items-center gap-4 mt-2 text-xs text-text-secondary">
            <span className="inline-flex items-center gap-1">
              <Calendar className="h-3.5 w-3.5" />
              Aangemaakt: {new Date(node.created_at).toLocaleDateString('nl-NL')}
            </span>
            <span className="inline-flex items-center gap-1">
              <LinkIcon className="h-3.5 w-3.5" />
              {node.edge_count ?? 0} verbindingen
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button variant="secondary" size="sm" icon={<Pencil className="h-4 w-4" />}>
            Bewerken
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<Trash2 className="h-4 w-4" />}
            onClick={handleDelete}
            className="text-red-500 hover:bg-red-50 hover:text-red-600"
          >
            Verwijder
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={clsx(
              'px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px',
              activeTab === tab.id
                ? 'border-primary-900 text-primary-900'
                : 'border-transparent text-text-secondary hover:text-text hover:border-border',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Description */}
            <Card>
              <h3 className="text-sm font-medium text-text mb-2">Beschrijving</h3>
              <p className="text-sm text-text-secondary whitespace-pre-wrap">
                {node.description || 'Geen beschrijving beschikbaar.'}
              </p>
            </Card>

            {/* Metadata */}
            {node.metadata && Object.keys(node.metadata).length > 0 && (
              <Card>
                <h3 className="text-sm font-medium text-text mb-3">Metadata</h3>
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {Object.entries(node.metadata).map(([key, value]) => (
                    <div key={key}>
                      <dt className="text-xs font-medium text-text-secondary capitalize">
                        {key.replace(/_/g, ' ')}
                      </dt>
                      <dd className="text-sm text-text mt-0.5">
                        {String(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </Card>
            )}

            {/* Stakeholders preview */}
            {stakeholders && stakeholders.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-text mb-3">
                  <Users className="h-4 w-4 inline mr-1.5 -mt-0.5" />
                  Betrokkenen ({stakeholders.length})
                </h3>
                <div className="space-y-2">
                  {stakeholders.slice(0, 5).map((s) => (
                    <PersonCardExpandable
                      key={s.id}
                      person={s.person}
                      extraBadge={
                        <Badge variant="slate">
                          {STAKEHOLDER_ROL_LABELS[s.rol] ?? s.rol}
                        </Badge>
                      }
                    />
                  ))}
                  {stakeholders.length > 5 && (
                    <button
                      onClick={() => setActiveTab('stakeholders')}
                      className="text-xs text-primary-700 hover:text-primary-900 transition-colors"
                    >
                      Bekijk alle {stakeholders.length} betrokkenen
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Connected nodes preview */}
            {neighbors && neighbors.length > 0 && (
              <Card>
                <h3 className="text-sm font-medium text-text mb-3">
                  Verbonden nodes ({neighbors.length})
                </h3>
                <div className="space-y-2">
                  {neighbors.slice(0, 5).map((neighbor) => (
                    <button
                      key={neighbor.id}
                      onClick={() => navigate(`/nodes/${neighbor.id}`)}
                      className="flex items-center gap-2 w-full p-2 rounded-lg hover:bg-gray-50 transition-colors text-left"
                    >
                      <Badge variant={NODE_TYPE_COLORS[neighbor.node_type] as 'blue'} dot title={nodeAltLabel(neighbor.node_type)}>
                        {nodeLabel(neighbor.node_type)}
                      </Badge>
                      <span className="text-sm text-text truncate">
                        {neighbor.title}
                      </span>
                    </button>
                  ))}
                  {neighbors.length > 5 && (
                    <button
                      onClick={() => setActiveTab('connections')}
                      className="text-xs text-primary-700 hover:text-primary-900 transition-colors"
                    >
                      Bekijk alle {neighbors.length} verbindingen
                    </button>
                  )}
                </div>
              </Card>
            )}
          </div>
        )}

        {activeTab === 'connections' && (
          <EdgeList nodeId={nodeId} />
        )}

        {activeTab === 'stakeholders' && (
          <div className="space-y-4">
            <h3 className="text-sm font-medium text-text">
              Betrokkenen ({stakeholders?.length ?? 0})
            </h3>
            {stakeholders && stakeholders.length > 0 ? (
              <div className="space-y-2">
                {stakeholders.map((s) => (
                  <PersonCardExpandable
                    key={s.id}
                    person={s.person}
                    extraBadge={
                      <Badge variant="slate">
                        {STAKEHOLDER_ROL_LABELS[s.rol] ?? s.rol}
                      </Badge>
                    }
                  />
                ))}
              </div>
            ) : (
              <EmptyState
                title="Geen betrokkenen"
                description="Er zijn nog geen personen gekoppeld aan deze node."
              />
            )}
          </div>
        )}

        {activeTab === 'tasks' && (
          <TaskView tasks={nodeTasks ?? []} defaultNodeId={nodeId} />
        )}

        {activeTab === 'activity' && (
          <EmptyState
            title="Activiteitentijdlijn"
            description="Hier verschijnt de activiteitsgeschiedenis van deze node."
          />
        )}
      </div>
    </div>
  );
}
