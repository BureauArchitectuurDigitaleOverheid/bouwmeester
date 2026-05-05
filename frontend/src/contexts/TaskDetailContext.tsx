import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { nextModalSeq } from '@/utils/modalSeq';

interface TaskDetailContextValue {
  openTaskDetail: (taskId: string, parentLabel?: string) => void;
  taskDetailId: string | null;
  taskParentLabel: string | null;
  closeTaskDetail: () => void;
  /** Monotonically increasing counter, bumped on every openTaskDetail call. */
  taskOpenSeq: number;
}

const TaskDetailContext = createContext<TaskDetailContextValue | null>(null);

/** No-op fallback for read-only / public contexts (e.g. /c/:slug page) where
 *  the provider isn't mounted but a child component (RichTextDisplay) still
 *  calls the hook. */
const NOOP_TASK_DETAIL: TaskDetailContextValue = {
  openTaskDetail: () => {},
  taskDetailId: null,
  taskParentLabel: null,
  closeTaskDetail: () => {},
  taskOpenSeq: 0,
};

export function useTaskDetail() {
  return useContext(TaskDetailContext) ?? NOOP_TASK_DETAIL;
}

export function TaskDetailProvider({ children }: { children: React.ReactNode }) {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [parentLabel, setParentLabel] = useState<string | null>(null);
  const [openSeq, setOpenSeq] = useState(0);
  const location = useLocation();

  const openTaskDetail = useCallback((id: string, label?: string) => {
    setTaskId(id);
    setParentLabel(label ?? null);
    setOpenSeq(nextModalSeq());
  }, []);

  const closeTaskDetail = useCallback(() => {
    setTaskId(null);
    setParentLabel(null);
  }, []);

  // Close modal on route change
  useEffect(() => {
    setTaskId(null);
    setParentLabel(null);
  }, [location.pathname]);

  return (
    <TaskDetailContext.Provider value={{ openTaskDetail, taskDetailId: taskId, taskParentLabel: parentLabel, closeTaskDetail, taskOpenSeq: openSeq }}>
      {children}
    </TaskDetailContext.Provider>
  );
}
