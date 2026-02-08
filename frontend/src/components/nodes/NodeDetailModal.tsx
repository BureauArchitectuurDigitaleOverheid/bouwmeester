import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Calendar, Link as LinkIcon, Pencil, ExternalLink } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { ReferencesList } from '@/components/common/ReferencesList';
import { NodeEditForm } from './NodeEditForm';
import { useNode } from '@/hooks/useNodes';
import { NODE_TYPE_COLORS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';

interface NodeDetailModalProps {
  nodeId: string | null;
  open: boolean;
  onClose: () => void;
}

export function NodeDetailModal({ nodeId, open, onClose }: NodeDetailModalProps) {
  const { data: node, isLoading } = useNode(nodeId ?? undefined);
  const [showEdit, setShowEdit] = useState(false);
  const navigate = useNavigate();
  const { nodeLabel, nodeAltLabel } = useVocabulary();

  if (!open) return null;

  if (showEdit && node) {
    return (
      <NodeEditForm
        open
        onClose={() => {
          setShowEdit(false);
          onClose();
        }}
        node={node}
      />
    );
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isLoading ? 'Laden...' : node?.title ?? 'Node niet gevonden'}
      size="lg"
      footer={
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={<Pencil className="h-4 w-4" />}
              onClick={() => setShowEdit(true)}
              disabled={!node}
            >
              Bewerken
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={<ExternalLink className="h-4 w-4" />}
              onClick={() => {
                onClose();
                navigate(`/nodes/${nodeId}`);
              }}
              disabled={!node}
            >
              Openen
            </Button>
          </div>
          <Button variant="secondary" onClick={onClose}>
            Sluiten
          </Button>
        </div>
      }
    >
      {isLoading ? (
        <div className="flex items-center justify-center py-8 text-text-secondary text-sm">
          Laden...
        </div>
      ) : !node ? (
        <div className="flex items-center justify-center py-8 text-text-secondary text-sm">
          Node niet gevonden.
        </div>
      ) : (
        <div className="space-y-5">
          {/* Type and status badges */}
          <div className="flex items-center gap-3 flex-wrap">
            <Badge variant={(NODE_TYPE_COLORS[node.node_type] ?? 'gray') as 'blue'} dot title={nodeAltLabel(node.node_type)}>
              {nodeLabel(node.node_type)}
            </Badge>
            {node.status && <Badge variant="gray">{node.status}</Badge>}
            {node.edge_count != null && (
              <span className="inline-flex items-center gap-1 text-sm text-text-secondary">
                <LinkIcon className="h-4 w-4" />
                {node.edge_count} verbindingen
              </span>
            )}
          </div>

          {/* Description */}
          <div>
            <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">
              Beschrijving
            </h4>
            <RichTextDisplay content={node.description} />
          </div>

          {/* References */}
          <ReferencesList targetId={node.id} />

          {/* Metadata grid */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Aangemaakt
              </h4>
              <span className="inline-flex items-center gap-1.5 text-text-secondary">
                <Calendar className="h-4 w-4" />
                {new Date(node.created_at).toLocaleDateString('nl-NL', {
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })}
              </span>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Laatst bijgewerkt
              </h4>
              <span className="inline-flex items-center gap-1.5 text-text-secondary">
                <Calendar className="h-4 w-4" />
                {new Date(node.updated_at).toLocaleDateString('nl-NL', {
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })}
              </span>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
