import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

interface TaskDetailContextValue {
  openTaskDetail: (taskId: string) => void;
  taskDetailId: string | null;
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
  const location = useLocation();

  const openTaskDetail = useCallback((id: string) => {
    setTaskId(id);
  }, []);

  const closeTaskDetail = useCallback(() => {
    setTaskId(null);
  }, []);

  // Close modal on route change
  useEffect(() => {
    setTaskId(null);
  }, [location.pathname]);

  return (
    <TaskDetailContext.Provider value={{ openTaskDetail, taskDetailId: taskId, closeTaskDetail }}>
      {children}
    </TaskDetailContext.Provider>
  );
}
