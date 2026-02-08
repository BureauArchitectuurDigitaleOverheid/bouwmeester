import { NavLink } from 'react-router-dom';
import { clsx } from 'clsx';
import {
  Inbox,
  Network,
  CheckSquare,
  Search,
  Building2,
  Users,
  ScrollText,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { useUIStore } from '@/store/ui';

const navItems = [
  { to: '/', icon: Inbox, label: 'Inbox' },
  { to: '/corpus', icon: Network, label: 'Corpus' },
  { to: '/tasks', icon: CheckSquare, label: 'Taken' },
  { to: '/organisatie', icon: Building2, label: 'Organisatie' },
  { to: '/eenheid-overzicht', icon: Users, label: 'Eenheid' },
  { to: '/moties', icon: ScrollText, label: 'Kamermoties' },
  { to: '/search', icon: Search, label: 'Zoeken' },
];

export function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useUIStore();

  return (
    <aside
      className={clsx(
        'flex flex-col bg-primary-900 text-white transition-all duration-300 ease-in-out h-screen sticky top-0',
        sidebarOpen ? 'w-60' : 'w-16',
      )}
    >
      {/* Logo / Brand */}
      <div className="flex items-center gap-3 px-4 h-16 border-b border-white/10 shrink-0">
        <div className="flex items-center justify-center h-8 w-8 rounded-lg bg-accent-500 shrink-0">
          <Building2 className="h-4.5 w-4.5 text-white" />
        </div>
        {sidebarOpen && (
          <span className="text-base font-semibold tracking-tight whitespace-nowrap">
            Bouwmeester
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150',
                isActive
                  ? 'bg-white/15 text-white'
                  : 'text-white/65 hover:bg-white/8 hover:text-white/90',
                !sidebarOpen && 'justify-center px-0',
              )
            }
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {sidebarOpen && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Collapse toggle */}
      <div className="px-2 py-3 border-t border-white/10 shrink-0">
        <button
          onClick={toggleSidebar}
          className={clsx(
            'flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm font-medium',
            'text-white/50 hover:bg-white/8 hover:text-white/80 transition-all duration-150',
            !sidebarOpen && 'justify-center px-0',
          )}
        >
          {sidebarOpen ? (
            <>
              <PanelLeftClose className="h-5 w-5 shrink-0" />
              <span>Inklappen</span>
            </>
          ) : (
            <PanelLeftOpen className="h-5 w-5 shrink-0" />
          )}
        </button>
      </div>
    </aside>
  );
}
