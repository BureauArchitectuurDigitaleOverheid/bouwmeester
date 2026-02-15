/**
 * Returns true if the person was active within the given threshold (default 5 minutes).
 * Accepts any object with a `last_seen_at` field (works with both Person and AdminUser).
 * Returns false for agents — bots shouldn't show "online" status.
 */
export function isPersonOnline(
  person: { last_seen_at?: string | null; is_agent?: boolean },
  thresholdMinutes = 5,
): boolean {
  if (person.is_agent) return false;
  if (!person.last_seen_at) return false;
  const diff = Date.now() - new Date(person.last_seen_at).getTime();
  return diff < thresholdMinutes * 60 * 1000;
}

/**
 * Format a timestamp as a Dutch relative time string (e.g. "2 min geleden").
 * Returns "-" if the timestamp is null/undefined.
 */
export function formatRelativeTime(timestamp?: string | null): string {
  if (!timestamp) return '-';
  const diffMs = Date.now() - new Date(timestamp).getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return 'zojuist';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} min geleden`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour} uur geleden`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay === 1) return 'gisteren';
  if (diffDay < 7) return `${diffDay} dagen geleden`;
  return new Date(timestamp).toLocaleDateString('nl-NL', { day: 'numeric', month: 'short' });
}
