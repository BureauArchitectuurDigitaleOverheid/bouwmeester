import { useState, useEffect, useRef } from 'react';
import { findSimilarNodes } from '@/api/search';
import { NODE_TYPE_LABELS, type SimilarNodeItem, type NodeType } from '@/types';

interface DuplicateWarningProps {
  title: string;
  excludeNodeId?: string;
}

export function DuplicateWarning({ title, excludeNodeId }: DuplicateWarningProps) {
  const [items, setItems] = useState<SimilarNodeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);

    const trimmed = title.trim();
    if (trimmed.length < 5) {
      setItems([]);
      return;
    }

    timerRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await findSimilarNodes(trimmed, excludeNodeId);
        setItems(res.items);
      } catch {
        setItems([]);
      } finally {
        setLoading(false);
      }
    }, 500);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [title, excludeNodeId]);

  if (loading) {
    return (
      <nldd-activity-indicator size="16" text="Controleren op vergelijkbare nodes..." show-text />
    );
  }

  if (items.length === 0) return null;

  return (
    <nldd-inline-dialog
      variant="alert"
      text="Vergelijkbare nodes gevonden"
      horizontal-alignment="left"
    >
      <nldd-list dividers="never">
        {items.map((item) => (
          <nldd-list-item key={item.id} href={`/nodes/${item.id}`} target="_blank">
            <nldd-text-cell width="fit-content" color="warning" text={NODE_TYPE_LABELS[item.node_type as NodeType] ?? item.node_type} />
            <nldd-text-cell text={item.title} />
            <nldd-text-cell width="fit-content" color="warning" text={`${Math.round(item.similarity * 100)}%`} />
          </nldd-list-item>
        ))}
      </nldd-list>
    </nldd-inline-dialog>
  );
}
