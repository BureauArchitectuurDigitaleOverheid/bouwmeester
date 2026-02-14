import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Trash2, ArrowRight } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { EmptyState } from '@/components/common/EmptyState';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { AddEdgeForm } from './AddEdgeForm';
import { useEdges, useDeleteEdge } from '@/hooks/useEdges';
import { NODE_TYPE_COLORS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';

interface EdgeListProps {
  nodeId: string;
}

export function EdgeList({ nodeId }: EdgeListProps) {
  const navigate = useNavigate();
  const { nodeLabel, nodeAltLabel, edgeLabel } = useVocabulary();
  const [showAddForm, setShowAddForm] = useState(false);
  const { data: edges = [], isLoading } = useEdges({ node_id: nodeId });
  const deleteEdge = useDeleteEdge();

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-text">
          Verbindingen ({edges.length})
        </h3>
        <Button
          variant="secondary"
          size="sm"
          icon={<Plus className="h-4 w-4" />}
          onClick={() => setShowAddForm(true)}
        >
          Verbinding toevoegen
        </Button>
      </div>

      {edges.length > 0 ? (
        <div className="space-y-2">
          {edges.map((edge) => {
            const connectedNode =
              edge.from_node_id === nodeId ? edge.to_node : edge.from_node;
            const direction = edge.from_node_id === nodeId ? 'outgoing' : 'incoming';

            return (
              <Card key={edge.id} padding={false}>
                <div className="flex items-center gap-3 px-4 py-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="slate">{edgeLabel(edge.edge_type_id)}</Badge>
                      <ArrowRight
                        className={`h-3.5 w-3.5 text-text-secondary ${
                          direction === 'incoming' ? 'rotate-180' : ''
                        }`}
                      />
                    </div>
                    {connectedNode && (
                      <button
                        onClick={() => navigate(`/nodes/${connectedNode.id}`)}
                        className="text-sm text-text hover:text-primary-700 transition-colors text-left"
                      >
                        <Badge
                          variant={NODE_TYPE_COLORS[connectedNode.node_type]}
                          className="mr-2"
                          title={nodeAltLabel(connectedNode.node_type)}
                        >
                          {nodeLabel(connectedNode.node_type)}
                        </Badge>
                        {connectedNode.title}
                      </button>
                    )}
                    {edge.description && (
                      <p className="text-xs text-text-secondary mt-1">
                        {edge.description}
                      </p>
                    )}
                  </div>

                  <button
                    onClick={() => deleteEdge.mutate(edge.id)}
                    className="p-1.5 rounded-lg text-text-secondary hover:text-red-500 hover:bg-red-50 transition-colors shrink-0"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <EmptyState
          title="Geen verbindingen"
          description="Deze node heeft nog geen verbindingen met andere nodes."
          action={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowAddForm(true)}
            >
              Eerste verbinding toevoegen
            </Button>
          }
        />
      )}

      <AddEdgeForm
        open={showAddForm}
        onClose={() => setShowAddForm(false)}
        sourceNodeId={nodeId}
      />
    </div>
  );
}
