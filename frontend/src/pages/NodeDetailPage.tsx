import { useParams } from 'react-router-dom';
import { NodeDetail } from '@/components/nodes/NodeDetail';

export function NodeDetailPage() {
  const { id } = useParams<{ id: string }>();

  if (!id) {
    return null;
  }

  return <NodeDetail nodeId={id} />;
}
