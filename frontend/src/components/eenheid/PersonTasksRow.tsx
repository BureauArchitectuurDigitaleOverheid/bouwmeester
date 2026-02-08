import { ChevronRight } from 'lucide-react';
import { TaskCard } from '@/components/tasks/TaskCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useTasksByPerson } from '@/hooks/useTasks';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import type { EenheidPersonTaskStats, Task } from '@/types';

interface PersonTasksRowProps {
  person: EenheidPersonTaskStats;
  isExpanded: boolean;
  onToggle: () => void;
}

export function PersonTasksRow({ person, isExpanded, onToggle }: PersonTasksRowProps) {
  const { data: tasks, isLoading } = useTasksByPerson(isExpanded ? person.person_id : null);
  const { openTaskDetail } = useTaskDetail();

  const handleTaskClick = (task: Task) => {
    openTaskDetail(task.id);
  };

  return (
    <>
      <tr
        className="border-b border-border last:border-0 hover:bg-gray-50 transition-colors cursor-pointer"
        onClick={onToggle}
      >
        <td className="px-5 py-3 font-medium text-text">
          <div className="flex items-center gap-2">
            <ChevronRight
              className={`h-4 w-4 text-text-secondary transition-transform ${
                isExpanded ? 'rotate-90' : ''
              }`}
            />
            {person.person_naam}
          </div>
        </td>
        <td className="px-5 py-3 text-right text-text-secondary">
          {person.open_count}
        </td>
        <td className="px-5 py-3 text-right text-text-secondary">
          {person.in_progress_count}
        </td>
        <td className="px-5 py-3 text-right text-text-secondary">
          {person.done_count}
        </td>
        <td
          className={`px-5 py-3 text-right font-medium ${
            person.overdue_count > 0
              ? 'text-red-600'
              : 'text-text-secondary'
          }`}
        >
          {person.overdue_count}
        </td>
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={5} className="px-5 py-3 bg-gray-50/50">
            {isLoading && <LoadingSpinner className="py-4" />}
            {tasks && tasks.length === 0 && (
              <p className="text-sm text-text-secondary py-2">Geen taken gevonden.</p>
            )}
            {tasks && tasks.length > 0 && (
              <div className="space-y-2">
                {tasks.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    onEdit={handleTaskClick}
                    compact
                  />
                ))}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
