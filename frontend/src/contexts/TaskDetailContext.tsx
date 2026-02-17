import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

interface TaskDetailContextValue {
  openTaskDetail: (taskId: string, parentLabel?: string) => void;
  taskDetailId: string | null;
  taskParentLabel: string | null;
  closeTaskDetail: () => void;
}

const TaskDetailContext = createContext<TaskDetailContextValue | null>(null);

export function useTaskDetail() {
  const ctx = useContext(TaskDetailContext);
  if (!ctx) throw new Error('useTaskDetail must be used within TaskDetailProvider');
  return ctx;
}

export function TaskDetailProvider({ children }: { children: React.ReactNode }) {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [parentLabel, setParentLabel] = useState<string | null>(null);
  const location = useLocation();

  const openTaskDetail = useCallback((id: string, label?: string) => {
    setTaskId(id);
    setParentLabel(label ?? null);
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
    <TaskDetailContext.Provider value={{ openTaskDetail, taskDetailId: taskId, taskParentLabel: parentLabel, closeTaskDetail }}>
      {children}
    </TaskDetailContext.Provider>
  );
}
