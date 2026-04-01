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
  Settings,
  Shield,
  PanelLeftClose,
  PanelLeftOpen,
  BookOpen,
  Banknote,
  Funnel,
} from 'lucide-react';
import logoImg from '/logo.png?url';
import { useUIStore } from '@/store/ui';
import { useAuth } from '@/contexts/AuthContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { usePermissions } from '@/hooks/usePermissions';
import { useManagedEenheden } from '@/hooks/useOrganisatie';
import { formatOrganisatieType } from '@/types';

interface SidebarProps {
  mobile?: boolean;
}

export function Sidebar({ mobile }: SidebarProps) {
  const { sidebarOpen, toggleSidebar, setMobileSidebarOpen } = useUIStore();
  const { person: authPerson } = useAuth();
  const { currentPerson } = useCurrentPerson();
  const { data: managedEenheden } = useManagedEenheden(currentPerson?.id);
  const { hasPermission, hasAnyPermission } = usePermissions();

  // On mobile the sidebar is always expanded (with labels)
  const expanded = mobile || sidebarOpen;

  const eenheidLabel = useMemo(() => {
    const first = managedEenheden?.[0];
    if (first) return formatOrganisatieType(first.type);
    return 'Eenheid';
  }, [managedEenheden]);

  const navItems = useMemo(() => {
    const items: { to: string; icon: typeof Inbox; label: string; permission?: string }[] = [
      { to: '/', icon: Inbox, label: 'Inbox' },
      { to: '/corpus', icon: Network, label: 'Corpus', permission: 'node:read' },
      { to: '/tasks', icon: CheckSquare, label: 'Taken', permission: 'task:read' },
      { to: '/organisatie', icon: Building2, label: 'Organisatie', permission: 'org:read' },
      { to: '/eenheid-overzicht', icon: Users, label: eenheidLabel, permission: 'org:read' },
      { to: '/opdrachten', icon: Banknote, label: 'Opdrachten', permission: 'opdracht:read' },
      { to: '/leads', icon: Funnel, label: 'Leads', permission: 'lead:read' },
      { to: '/parlementair', icon: ScrollText, label: 'Kamerstukken', permission: 'node:read' },
      { to: '/search', icon: Search, label: 'Zoeken' },
      { to: '/docs', icon: BookOpen, label: 'Handleiding' },
    ];
    return items.filter((item) => !item.permission || hasPermission(item.permission));
  }, [eenheidLabel, hasPermission]);

  const bottomNavItems = useMemo(() => {
    const items = [
      { to: '/instellingen', icon: Settings, label: 'Instellingen' },
    ];
    const canAdmin = hasAnyPermission(
      'whitelist:manage',
      'people:manage',
      'config:manage',
      'database:backup',
      'people:assign_role',
      'org:manage',
    );
    const isManager = (authPerson?.managed_eenheden?.length ?? 0) > 0;
    if (hasPermission('audit:read')) {
      items.push({ to: '/auditlog', icon: History, label: 'Auditlog' });
    }
    if (canAdmin) {
      items.push({ to: '/admin', icon: Shield, label: 'Beheer' });
    } else if (isManager) {
      items.push({ to: '/admin?tab=placements', icon: Shield, label: 'Beheer' });
    }
    return items;
  }, [authPerson?.managed_eenheden, hasPermission, hasAnyPermission]);

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
        <img src={logoImg} alt="Bouwmeester" className="h-8 w-8 rounded-lg shrink-0" />
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
