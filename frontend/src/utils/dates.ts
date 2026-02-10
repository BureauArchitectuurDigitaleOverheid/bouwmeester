import { format, formatDistanceToNowStrict } from 'date-fns';
import { nl } from 'date-fns/locale';

/** "15 jan" — compact date for cards/lists */
export function formatDateShort(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  return format(new Date(dateStr), 'd MMM', { locale: nl });
}

/** "15 januari 2025" — full date for detail views */
export function formatDateLong(dateStr: string): string {
  return format(new Date(dateStr), 'd MMMM yyyy', { locale: nl });
}

/** "15-1-2025" — default locale format */
export function formatDate(dateStr: string): string {
  return format(new Date(dateStr), 'P', { locale: nl });
}

/** "15 jan, 10:30" — date + time for inbox items */
export function formatDateTimeShort(dateStr: string): string {
  return format(new Date(dateStr), 'd MMM, HH:mm', { locale: nl });
}

/** "Zojuist" / "5 minuten geleden" / "3 uur geleden" — relative time */
export function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 60_000) return 'Zojuist';
  return formatDistanceToNowStrict(date, { addSuffix: true, locale: nl });
}

/** Check if a due_date string is before today */
export function isOverdue(dueDateStr: string): boolean {
  const dueDate = new Date(dueDateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return dueDate < today;
}

/** Today as "YYYY-MM-DD" for form defaults */
export function todayISO(): string {
  return format(new Date(), 'yyyy-MM-dd');
}
