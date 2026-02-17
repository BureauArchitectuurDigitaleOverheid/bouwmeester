import { useRef } from 'react';
import { TaskDetailModal } from '@/components/tasks/TaskDetailModal';
import { NodeDetailModal } from '@/components/nodes/NodeDetailModal';
import { OpdrachtDetailModal } from '@/components/opdrachten/OpdrachtDetailModal';
import { OpdrachtCreateModal } from '@/components/opdrachten/OpdrachtCreateModal';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useOpdrachtDetail } from '@/contexts/OpdrachtDetailContext';

const BASE_Z = 50;

/**
 * Dynamic stacking: the most recently opened modal gets the highest z-index.
 *
 * We maintain a stack (ref) of modal keys in order of opening.
 * On every render we reconcile: newly-open modals are pushed to the top,
 * closed modals are removed. This is done synchronously so the z-index
 * values are correct in the same render pass.
 */
export function DetailModals() {
  const { taskDetailId, closeTaskDetail } = useTaskDetail();
  const { nodeDetailId, closeNodeDetail } = useNodeDetail();
  const { opdrachtDetailId, closeOpdrachtDetail } = useOpdrachtDetail();

  const stackRef = useRef<string[]>([]);

  // Reconcile stack synchronously during render
  const openSet: Record<string, boolean> = {
    opdracht: !!opdrachtDetailId,
    node: !!nodeDetailId,
    task: !!taskDetailId,
  };

  // Remove closed modals
  let stack = stackRef.current.filter((key) => openSet[key]);

  // Push newly opened modals to the top
  for (const key of ['opdracht', 'node', 'task']) {
    if (openSet[key] && !stack.includes(key)) {
      stack = [...stack, key];
    }
  }

  stackRef.current = stack;

  function zIndexFor(key: string): number {
    const idx = stack.indexOf(key);
    return idx === -1 ? BASE_Z : BASE_Z + (idx + 1) * 10;
  }

  return (
    <>
      <OpdrachtCreateModal />
      <OpdrachtDetailModal
        opdrachtId={opdrachtDetailId}
        open={!!opdrachtDetailId}
        onClose={closeOpdrachtDetail}
        zIndex={zIndexFor('opdracht')}
      />
      <NodeDetailModal
        nodeId={nodeDetailId}
        open={!!nodeDetailId}
        onClose={closeNodeDetail}
        zIndex={zIndexFor('node')}
      />
      <TaskDetailModal
        taskId={taskDetailId}
        open={!!taskDetailId}
        onClose={closeTaskDetail}
        zIndex={zIndexFor('task')}
      />
    </>
  );
}
