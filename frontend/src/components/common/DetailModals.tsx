import { TaskDetailModal } from '@/components/tasks/TaskDetailModal';
import { NodeDetailModal } from '@/components/nodes/NodeDetailModal';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';

export function DetailModals() {
  const { taskDetailId, closeTaskDetail } = useTaskDetail();
  const { nodeDetailId, closeNodeDetail } = useNodeDetail();

  return (
    <>
      <TaskDetailModal
        taskId={taskDetailId}
        open={!!taskDetailId}
        onClose={closeTaskDetail}
      />
      <NodeDetailModal
        nodeId={nodeDetailId}
        open={!!nodeDetailId}
        onClose={closeNodeDetail}
      />
    </>
  );
}
