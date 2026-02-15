import { User, Bot } from 'lucide-react';
import { isPersonOnline } from '@/utils/people';

interface PersonAvatarProps {
  person: { naam: string; is_agent: boolean; last_seen_at?: string | null };
  /** Tailwind h-/w- size class, e.g. "h-10 w-10". Defaults to "h-10 w-10". */
  size?: string;
  /** Icon size class, e.g. "h-5 w-5". Defaults to "h-5 w-5". */
  iconSize?: string;
  /** Agent avatar color classes. Defaults to "bg-purple-100 text-purple-700". */
  agentColor?: string;
}

export function PersonAvatar({
  person,
  size = 'h-10 w-10',
  iconSize = 'h-5 w-5',
  agentColor = 'bg-purple-100 text-purple-700',
}: PersonAvatarProps) {
  const initials = person.naam
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  const online = isPersonOnline(person);

  return (
    <div className="relative shrink-0">
      {person.is_agent ? (
        <div className={`flex items-center justify-center ${size} rounded-full ${agentColor}`}>
          <Bot className={iconSize} />
        </div>
      ) : (
        <div className={`flex items-center justify-center ${size} rounded-full bg-primary-100 text-primary-700 font-semibold text-sm`}>
          {initials || <User className={iconSize} />}
        </div>
      )}
      {online && (
        <span className="absolute bottom-0 right-0 block h-2.5 w-2.5 rounded-full bg-green-500 ring-2 ring-white" />
      )}
    </div>
  );
}
