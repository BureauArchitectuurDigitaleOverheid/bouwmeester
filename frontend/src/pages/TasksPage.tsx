import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { TaskView } from '@/components/tasks/TaskView';
import { useTasks } from '@/hooks/useTasks';

export function TasksPage() {
  const { data: tasks, isLoading } = useTasks();

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  return <TaskView tasks={tasks ?? []} />;
}
