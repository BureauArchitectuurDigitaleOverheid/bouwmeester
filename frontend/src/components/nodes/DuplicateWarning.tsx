import { useState, useEffect, useRef } from 'react';
import { AlertTriangle, ExternalLink, Loader2 } from 'lucide-react';
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
      <div className="flex items-center gap-1.5 text-xs text-text-secondary">
        <Loader2 className="h-3 w-3 animate-spin" />
        Controleren op vergelijkbare nodes...
      </div>
    );
  }

  if (items.length === 0) return null;

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-3">
      <div className="flex items-center gap-1.5 mb-2">
        <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
        <span className="text-xs font-medium text-amber-800">
          Vergelijkbare nodes gevonden
        </span>
      </div>
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item.id} className="flex items-center gap-2 text-xs">
            <span className="text-amber-700 font-medium">
              {NODE_TYPE_LABELS[item.node_type as NodeType] ?? item.node_type}
            </span>
            <a
              href={`/nodes/${item.id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-amber-800 hover:text-amber-900 underline truncate flex items-center gap-1"
              onClick={(e) => e.stopPropagation()}
            >
              {item.title}
              <ExternalLink className="h-3 w-3 shrink-0" />
            </a>
            <span className="text-amber-600 shrink-0">
              {Math.round(item.similarity * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
