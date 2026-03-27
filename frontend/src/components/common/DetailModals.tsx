import { TaskDetailModal } from '@/components/tasks/TaskDetailModal';
import { NodeDetailModal } from '@/components/nodes/NodeDetailModal';
import { OpdrachtDetailModal } from '@/components/opdrachten/OpdrachtDetailModal';
import { OpdrachtCreateModal } from '@/components/opdrachten/OpdrachtCreateModal';
import { LeadDetailPanel } from '@/components/leads/LeadDetailPanel';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useOpdrachtDetail } from '@/contexts/OpdrachtDetailContext';
import { useLeadDetail } from '@/contexts/LeadDetailContext';

const BASE_Z = 50;

/**
 * Dynamic stacking: the most recently triggered modal gets the highest z-index.
 *
 * Each context exposes a monotonically increasing `openSeq` counter that bumps
 * on every `open*Detail()` call. We sort open modals by their seq — the modal
 * with the highest seq was opened most recently and gets the highest z-index.
 * This correctly handles:
 *  - Opening a fresh modal (new entry, highest seq → top)
 *  - Re-opening a modal that was already open underneath (seq bumps → moves to top)
 *  - Opening the same modal with a different ID (seq bumps → moves to top)
 */
export function DetailModals() {
  const { taskDetailId, closeTaskDetail, taskOpenSeq } = useTaskDetail();
  const { nodeDetailId, closeNodeDetail, nodeOpenSeq } = useNodeDetail();
  const { opdrachtDetailId, closeOpdrachtDetail, opdrachtOpenSeq } = useOpdrachtDetail();
  const { leadDetailId, closeLeadDetail, leadOpenSeq } = useLeadDetail();

  const modals = [
    { key: 'opdracht', open: !!opdrachtDetailId, seq: opdrachtOpenSeq },
    { key: 'node', open: !!nodeDetailId, seq: nodeOpenSeq },
    { key: 'task', open: !!taskDetailId, seq: taskOpenSeq },
    { key: 'lead', open: !!leadDetailId, seq: leadOpenSeq },
  ];

  // Sort open modals by seq (ascending) — last element gets highest z-index
  const openModals = modals
    .filter((m) => m.open)
    .sort((a, b) => a.seq - b.seq);

  function zIndexFor(key: string): number {
    const idx = openModals.findIndex((m) => m.key === key);
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
      <LeadDetailPanel
        leadId={leadDetailId}
        open={!!leadDetailId}
        onClose={closeLeadDetail}
        zIndex={zIndexFor('lead')}
      />
    </>
  );
}
