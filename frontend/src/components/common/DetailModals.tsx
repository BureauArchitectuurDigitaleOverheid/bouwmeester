import { TaskDetailModal } from '@/components/tasks/TaskDetailModal';
import { NodeDetailModal } from '@/components/nodes/NodeDetailModal';
import { OpdrachtDetailModal } from '@/components/opdrachten/OpdrachtDetailModal';
import { OpdrachtCreateModal } from '@/components/opdrachten/OpdrachtCreateModal';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useOpdrachtDetail } from '@/contexts/OpdrachtDetailContext';

/**
 * Stacking order: opdracht-create (45) → opdracht-detail (50) → node (60) → task (70).
 * This ensures modals opened from other modals appear on top.
 */
export function DetailModals() {
  const { taskDetailId, closeTaskDetail } = useTaskDetail();
  const { nodeDetailId, closeNodeDetail } = useNodeDetail();
  const { opdrachtDetailId, closeOpdrachtDetail } = useOpdrachtDetail();

  return (
    <>
      <OpdrachtCreateModal />
      <OpdrachtDetailModal
        opdrachtId={opdrachtDetailId}
        open={!!opdrachtDetailId}
        onClose={closeOpdrachtDetail}
        zIndex={50}
      />
      <NodeDetailModal
        nodeId={nodeDetailId}
        open={!!nodeDetailId}
        onClose={closeNodeDetail}
        zIndex={60}
      />
      <TaskDetailModal
        taskId={taskDetailId}
        open={!!taskDetailId}
        onClose={closeTaskDetail}
        zIndex={70}
      />
    </>
  );
}
