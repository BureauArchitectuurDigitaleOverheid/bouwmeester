import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Modal } from '@/components/common/Modal';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { useNodes } from '@/hooks/useNodes';
import { createEdge } from '@/api/edges';
import { queryKeys } from '@/hooks/queryKeys';
import { NODE_TYPE_LABELS, NODE_TYPE_COLORS, type NodeType } from '@/types';
import { useToast } from '@/contexts/ToastContext';
import { EDGE_TYPE_ONDERDEEL_VAN } from './constants';

interface LinkExistingNodeModalProps {
  open: boolean;
  onClose: () => void;
  dossierId: string;
  nodeType: NodeType;
  excludeNodeIds?: Set<string>;
}

export function LinkExistingNodeModal({ open, onClose, dossierId, nodeType, excludeNodeIds }: LinkExistingNodeModalProps) {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [isLinking, setIsLinking] = useState(false);
  const queryClient = useQueryClient();
  const { showError } = useToast();

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Server-side filtered query, excluding already-linked nodes
  const { data: nodes, isLoading } = useNodes(nodeType, debouncedSearch || undefined);
  const filteredNodes = (nodes ?? []).filter((n) => !excludeNodeIds?.has(n.id));

  const handleLink = async (targetNodeId: string) => {
    setIsLinking(true);
    try {
      await createEdge({
        from_node_id: targetNodeId,
        to_node_id: dossierId,
        edge_type_id: EDGE_TYPE_ONDERDEEL_VAN,
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.nodes.graph(dossierId, 2) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.nodes.neighbors(dossierId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.edges.all });
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Onbekende fout';
      showError(`Koppelen mislukt: ${msg}`);
    } finally {
      setIsLinking(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${NODE_TYPE_LABELS[nodeType]} koppelen aan dossier`}
      footer={
        <Button variant="secondary" onClick={onClose}>
          Annuleren
        </Button>
      }
    >
      <div className="space-y-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Zoek ${NODE_TYPE_LABELS[nodeType].toLowerCase()}...`}
          className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-border focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
          autoFocus
        />

        {isLoading ? (
          <p className="text-sm text-text-secondary text-center py-4">Laden...</p>
        ) : filteredNodes.length === 0 ? (
          <p className="text-sm text-text-secondary text-center py-4">
            Geen {NODE_TYPE_LABELS[nodeType].toLowerCase()} gevonden.
          </p>
        ) : (
          <div className="max-h-72 overflow-y-auto space-y-1">
            {filteredNodes.map((node) => (
              <button
                key={node.id}
                onClick={() => handleLink(node.id)}
                disabled={isLinking}
                className="flex items-center gap-2 w-full p-2.5 rounded-lg hover:bg-gray-50 transition-colors text-left disabled:opacity-50"
              >
                <Badge variant={NODE_TYPE_COLORS[nodeType]} dot>
                  {NODE_TYPE_LABELS[nodeType]}
                </Badge>
                <span className="text-sm text-text truncate flex-1">{node.title}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}
