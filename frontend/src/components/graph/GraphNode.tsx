import { memo } from 'react';
import { Handle, Position } from 'reactflow';
import type { NodeProps } from 'reactflow';
import { NodeType, NODE_TYPE_HEX_COLORS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';

const NODE_TYPE_BG_COLORS: Record<string, string> = {
  [NodeType.DOSSIER]: '#EFF6FF',
  [NodeType.DOEL]: '#ECFDF5',
  [NodeType.INSTRUMENT]: '#F5F3FF',
  [NodeType.BELEIDSKADER]: '#FFFBEB',
  [NodeType.MAATREGEL]: '#ECFEFF',
  [NodeType.POLITIEKE_INPUT]: '#FFF1F2',
  [NodeType.PROBLEEM]: '#FEF2F2',
  [NodeType.EFFECT]: '#ECFDF5',
  [NodeType.BELEIDSOPTIE]: '#EEF2FF',
  [NodeType.BRON]: '#FFF7ED',
  [NodeType.NOTITIE]: '#F8FAFC',
  [NodeType.OVERIG]: '#F9FAFB',
};

export interface GraphNodeData {
  label: string;
  description?: string;
  nodeType: NodeType;
  onClick?: () => void;
}

function GraphNodeComponent({ data }: NodeProps<GraphNodeData>) {
  const { nodeLabel } = useVocabulary();
  const color = NODE_TYPE_HEX_COLORS[data.nodeType] ?? '#9ca3af';
  const bgColor = NODE_TYPE_BG_COLORS[data.nodeType] ?? '#F9FAFB';
  const label = nodeLabel(data.nodeType);

  return (
    <div
      onClick={data.onClick}
      style={{
        background: '#ffffff',
        borderRadius: '10px',
        boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1)',
        border: `1px solid ${color}33`,
        minWidth: '180px',
        maxWidth: '240px',
        cursor: 'pointer',
        overflow: 'hidden',
      }}
    >
      {/* Colored top bar */}
      <div
        style={{
          height: '4px',
          background: color,
          borderRadius: '10px 10px 0 0',
        }}
      />

      <div style={{ padding: '10px 12px' }}>
        {/* Type badge */}
        <div
          style={{
            display: 'inline-block',
            padding: '1px 8px',
            borderRadius: '9999px',
            fontSize: '10px',
            fontWeight: 600,
            color: color,
            background: bgColor,
            marginBottom: '6px',
            letterSpacing: '0.025em',
            textTransform: 'uppercase',
          }}
        >
          {label}
        </div>

        {/* Title */}
        <div
          style={{
            fontSize: '13px',
            fontWeight: 500,
            color: '#1A1A2E',
            lineHeight: '1.4',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
          }}
        >
          {data.label}
        </div>
      </div>

      <Handle
        type="target"
        position={Position.Top}
        style={{
          width: '8px',
          height: '8px',
          background: color,
          border: '2px solid white',
          top: '-4px',
        }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        style={{
          width: '8px',
          height: '8px',
          background: color,
          border: '2px solid white',
          bottom: '-4px',
        }}
      />
    </div>
  );
}

export const GraphNode = memo(GraphNodeComponent);
