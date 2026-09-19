import { TaskDetailModal } from '@/components/tasks/TaskDetailModal';
import { NodeDetailModal } from '@/components/nodes/NodeDetailModal';
import { OpdrachtDetailModal } from '@/components/opdrachten/OpdrachtDetailModal';
import { OpdrachtCreateModal } from '@/components/opdrachten/OpdrachtCreateModal';
import { LeadDetailPanel } from '@/components/leads/LeadDetailPanel';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import { useOpdrachtDetail } from '@/contexts/OpdrachtDetailContext';
import { useLeadDetail } from '@/contexts/LeadDetailContext';


/**
 * The four detail surfaces, mounted once and driven by their contexts.
 *
 * Stacking is the browser's now. These are native `<dialog>` elements, so the
 * last one opened is on top by definition, including when one is re-opened
 * from underneath another — the three cases the hand-rolled ordering here used
 * to enumerate.
 */
export function DetailModals() {
  const { taskDetailId, closeTaskDetail } = useTaskDetail();
  const { nodeDetailId, closeNodeDetail } = useNodeDetail();
  const { opdrachtDetailId, closeOpdrachtDetail } = useOpdrachtDetail();
  const { leadDetailId, closeLeadDetail } = useLeadDetail();

  // The stacking order used to be computed here, from an open-sequence per
  // modal, and handed down as a `zIndex` prop. `nldd-window` is a native
  // `<dialog>`, so the browser's top layer decides: the last one opened is on
  // top, by definition. The computation stayed behind after the conversion,
  // sorting on every render to produce numbers nothing read.
  //
  // The `*OpenSeq` values the contexts still expose have no other reader; they
  // can go with the contexts themselves rather than inside this PR.

  return (
    <>
      <OpdrachtCreateModal />
      <OpdrachtDetailModal
        opdrachtId={opdrachtDetailId}
        open={!!opdrachtDetailId}
        onClose={closeOpdrachtDetail}
      />
      <NodeDetailModal
        nodeId={nodeDetailId}
        open={!!nodeDetailId}
        onClose={closeNodeDetail}
      />
      <TaskDetailModal
        taskId={taskDetailId}
        open={!!taskDetailId}
        onClose={closeTaskDetail}
      />
      <LeadDetailPanel
        leadId={leadDetailId}
        open={!!leadDetailId}
        onClose={closeLeadDetail}
      />
    </>
  );
}
