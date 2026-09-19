import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { TaskView } from '@/components/tasks/TaskView';
import { useTasks } from '@/hooks/useTasks';

export function TasksPage() {
  const { data: tasks, isLoading } = useTasks();

  if (isLoading) {
    return (
      <nldd-container padding="32">
        <LoadingSpinner />
      </nldd-container>
    );
  }

  return <TaskView tasks={tasks ?? []} />;
}
