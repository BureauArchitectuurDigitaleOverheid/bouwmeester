import { useMemo } from 'react';
import { AlertTriangle, CalendarDays, Calendar, Clock } from 'lucide-react';
import { TaskCard } from './TaskCard';
import { TaskStatus } from '@/types';
import type { Task } from '@/types';

interface TaskPersonalViewProps {
  tasks: Task[];
  onEditTask: (task: Task) => void;
}

interface TaskGroup {
  key: string;
  label: string;
  icon: React.ReactNode;
  tasks: Task[];
  headerClass?: string;
}

export function TaskPersonalView({ tasks, onEditTask }: TaskPersonalViewProps) {
  const groups = useMemo<TaskGroup[]>(() => {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const todayEnd = new Date(todayStart);
    todayEnd.setDate(todayEnd.getDate() + 1);
    const weekEnd = new Date(todayStart);
    weekEnd.setDate(weekEnd.getDate() + 8); // end of "next 7 days after today"

    const overdue: Task[] = [];
    const today: Task[] = [];
    const thisWeek: Task[] = [];
    const later: Task[] = [];

    for (const task of tasks) {
      const isDone = task.status === TaskStatus.DONE || task.status === TaskStatus.CANCELLED;

      if (!task.due_date) {
        later.push(task);
        continue;
      }

      const dueDate = new Date(task.due_date);

      if (dueDate < todayStart && !isDone) {
        overdue.push(task);
      } else if (dueDate >= todayStart && dueDate < todayEnd) {
        today.push(task);
      } else if (dueDate >= todayEnd && dueDate < weekEnd) {
        thisWeek.push(task);
      } else {
        later.push(task);
      }
    }

    return [
      {
        key: 'overdue',
        label: 'Verlopen',
        icon: <AlertTriangle className="h-4 w-4 text-red-500" />,
        tasks: overdue,
        headerClass: 'text-red-700',
      },
      {
        key: 'today',
        label: 'Vandaag',
        icon: <CalendarDays className="h-4 w-4 text-blue-500" />,
        tasks: today,
      },
      {
        key: 'week',
        label: 'Deze week',
        icon: <Calendar className="h-4 w-4 text-amber-500" />,
        tasks: thisWeek,
      },
      {
        key: 'later',
        label: 'Later',
        icon: <Clock className="h-4 w-4 text-text-secondary" />,
        tasks: later,
      },
    ];
  }, [tasks]);

  return (
    <div className="space-y-6">
      {groups.map((group) =>
        group.tasks.length > 0 ? (
          <section key={group.key}>
            <div className="flex items-center gap-2 mb-3">
              {group.icon}
              <h3 className={`text-sm font-semibold ${group.headerClass ?? 'text-text'}`}>
                {group.label}
              </h3>
              <span className="inline-flex items-center justify-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-text-secondary">
                {group.tasks.length}
              </span>
            </div>
            <div className="space-y-2">
              {group.tasks.map((task) => (
                <TaskCard key={task.id} task={task} onEdit={onEditTask} />
              ))}
            </div>
          </section>
        ) : null,
      )}

      {/* Empty state when no tasks at all */}
      {groups.every((g) => g.tasks.length === 0) && (
        <p className="text-sm text-text-secondary italic py-4 text-center">
          Geen taken gevonden.
        </p>
      )}
    </div>
  );
}
