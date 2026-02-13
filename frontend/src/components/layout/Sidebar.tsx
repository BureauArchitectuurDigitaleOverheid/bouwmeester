import { useMemo } from 'react';
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
  History,
  Shield,
  PanelLeftClose,
  PanelLeftOpen,
  BookOpen,
} from 'lucide-react';
import { useUIStore } from '@/store/ui';
import { useAuth } from '@/contexts/AuthContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useManagedEenheden } from '@/hooks/useOrganisatie';
import { ORGANISATIE_TYPE_LABELS } from '@/types';

interface SidebarProps {
  mobile?: boolean;
}

export function Sidebar({ mobile }: SidebarProps) {
  const { sidebarOpen, toggleSidebar, setMobileSidebarOpen } = useUIStore();
  const { person: authPerson, oidcConfigured } = useAuth();
  const { currentPerson } = useCurrentPerson();
  const { data: managedEenheden } = useManagedEenheden(currentPerson?.id);

  // On mobile the sidebar is always expanded (with labels)
  const expanded = mobile || sidebarOpen;

  const eenheidLabel = useMemo(() => {
    const first = managedEenheden?.[0];
    if (first) return ORGANISATIE_TYPE_LABELS[first.type] ?? 'Eenheid';
    return 'Eenheid';
  }, [managedEenheden]);

  const navItems = useMemo(() => {
    return [
      { to: '/', icon: Inbox, label: 'Inbox' },
      { to: '/corpus', icon: Network, label: 'Corpus' },
      { to: '/tasks', icon: CheckSquare, label: 'Taken' },
      { to: '/organisatie', icon: Building2, label: 'Organisatie' },
      { to: '/eenheid-overzicht', icon: Users, label: eenheidLabel },
      { to: '/parlementair', icon: ScrollText, label: 'Kamerstukken' },
      { to: '/search', icon: Search, label: 'Zoeken' },
      { to: '/docs', icon: BookOpen, label: 'Documentatie' },
    ];
  }, [eenheidLabel]);

  const bottomNavItems = useMemo(() => {
    const items = [
      { to: '/auditlog', icon: History, label: 'Auditlog' },
    ];
    if (!oidcConfigured || authPerson?.is_admin) {
      items.push({ to: '/admin', icon: Shield, label: 'Beheer' });
    }
    return items;
  }, [oidcConfigured, authPerson?.is_admin]);

  const handleNavClick = () => {
    if (mobile) {
      setMobileSidebarOpen(false);
    }
  };

  return (
    <aside
      className={clsx(
        'flex flex-col bg-primary-900 text-white transition-all duration-300 ease-in-out',
        mobile ? 'w-72 h-full' : 'h-screen sticky top-0',
        !mobile && (expanded ? 'w-60' : 'w-16'),
      )}
    >
      {/* Logo / Brand + Collapse toggle */}
      <div className={clsx(
        'flex items-center border-b border-white/10 shrink-0',
        expanded ? 'gap-3 px-4 h-16' : 'flex-col gap-1 px-2 py-3',
      )}>
        <div className="flex items-center justify-center h-8 w-8 rounded-lg bg-accent-500 shrink-0">
          <Building2 className="h-4.5 w-4.5 text-white" />
        </div>
        {expanded && (
          <span className="text-base font-semibold tracking-tight whitespace-nowrap flex-1">
            Bouwmeester
          </span>
        )}
        {!mobile && (
          <button
            onClick={toggleSidebar}
            className={clsx(
              'flex items-center justify-center rounded-lg text-white/50 hover:bg-white/8 hover:text-white/80 transition-all duration-150 shrink-0',
              expanded ? 'h-8 w-8' : 'h-8 w-8',
            )}
          >
            {expanded ? (
              <PanelLeftClose className="h-5 w-5" />
            ) : (
              <PanelLeftOpen className="h-5 w-5" />
            )}
          </button>
        )}
      </div>

      {/* Main navigation */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            onClick={handleNavClick}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-3 md:py-2.5 rounded-xl text-sm font-medium transition-all duration-150',
                isActive
                  ? 'bg-white/15 text-white'
                  : 'text-white/65 hover:bg-white/8 hover:text-white/90',
                !expanded && 'justify-center px-0',
              )
            }
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {expanded && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Bottom navigation — Auditlog & Beheer */}
      <div className="px-2 py-3 border-t border-white/10 shrink-0 space-y-0.5">
        {bottomNavItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            onClick={handleNavClick}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-3 md:py-2.5 rounded-xl text-sm font-medium transition-all duration-150',
                isActive
                  ? 'bg-white/15 text-white'
                  : 'text-white/65 hover:bg-white/8 hover:text-white/90',
                !expanded && 'justify-center px-0',
              )
            }
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {expanded && <span>{item.label}</span>}
          </NavLink>
        ))}

      </div>
    </aside>
  );
}
