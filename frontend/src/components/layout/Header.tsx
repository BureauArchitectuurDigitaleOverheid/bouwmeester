import { useState, useRef, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Search, User, ChevronDown, Check, LogOut, Menu, Eye, EyeOff } from 'lucide-react';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { useAuth } from '@/contexts/AuthContext';
import { VOCABULARY_LABELS, type VocabularyId } from '@/vocabulary';
import { NotificationBell } from '@/components/common/NotificationBell';
import { useManagedEenheden } from '@/hooks/useOrganisatie';
import { ORGANISATIE_TYPE_LABELS, formatFunctie } from '@/types';
import { useUIStore } from '@/store/ui';
import { useFeatureToggle } from '@/contexts/FeatureToggleContext';

const pageTitles: Record<string, string> = {
  '/': 'Inbox',
  '/corpus': 'Corpus',
  '/tasks': 'Taken',
  '/people': 'Personen',
  '/organisatie': 'Organisatie',
  '/parlementair': 'Kamerstukken',
  '/opdrachten': 'Opdrachten & Subsidies',
  '/externe-organisaties': 'Externe Organisaties',
  '/admin': 'Beheer',
  '/instellingen': 'Instellingen',
  '/auditlog': 'Auditlog',
  '/search': 'Zoeken',
  '/docs': 'Documentatie',
  '/leads': 'Leads',
};

function getInitials(naam: string): string {
  return naam
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

export function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const { currentPerson, setDevPersonId, people } = useCurrentPerson();
  const { vocabularyId, setVocabularyId } = useVocabulary();
  const { authenticated, oidcConfigured, logout, realIsAdmin, viewAsNonAdmin, toggleViewAsNonAdmin } = useAuth();
  const toggleMobileSidebar = useUIStore((s) => s.toggleMobileSidebar);
  const { isFeatureEnabled } = useFeatureToggle();

  // Dev-mode person picker state (only used when !oidcConfigured)
  const [showDevPicker, setShowDevPicker] = useState(false);
  const [search, setSearch] = useState('');
  const pickerRef = useRef<HTMLDivElement>(null);

  const { data: managedEenheden } = useManagedEenheden(currentPerson?.id);

  const pathBase = '/' + (location.pathname.split('/')[1] || '');
  const eenheidTitle = (() => {
    const first = managedEenheden?.[0];
    if (first) {
      const label = ORGANISATIE_TYPE_LABELS[first.type] ?? first.type;
      return `${label} Overzicht`;
    }
    return 'Eenheid Overzicht';
  })();
  const title = pathBase === '/eenheid-overzicht'
    ? eenheidTitle
    : pageTitles[pathBase] || 'Bouwmeester';

  const isDetailPage = location.pathname.match(/^\/nodes\/.+/);
  const breadcrumbs = isDetailPage
    ? [
        { label: 'Corpus', href: '/corpus' },
        { label: 'Detail', href: undefined },
      ]
    : undefined;

  // Close picker on outside click
  useEffect(() => {
    if (!showDevPicker) return;
    const handleClick = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowDevPicker(false);
        setSearch('');
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showDevPicker]);

  const filteredPeople = people.filter((p) =>
    p.naam.toLowerCase().includes(search.toLowerCase()),
  );

  const initials = currentPerson ? getInitials(currentPerson.naam) : null;

  return (
    <header className="flex items-center justify-between h-16 px-4 md:px-6 bg-surface border-b border-border shrink-0 sticky top-0 z-30">
      {/* Left: Hamburger + Title / Breadcrumbs */}
      <div className="flex items-center gap-2 min-w-0 shrink">
        <button
          onClick={toggleMobileSidebar}
          className="md:hidden flex items-center justify-center h-9 w-9 -ml-1 rounded-lg text-text-secondary hover:bg-gray-100 hover:text-text transition-colors shrink-0"
        >
          <Menu className="h-5 w-5" />
        </button>
        {breadcrumbs ? (
          <nav className="flex items-center gap-1.5 text-sm min-w-0">
            {breadcrumbs.map((crumb, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-text-secondary">/</span>}
                {crumb.href ? (
                  <button
                    onClick={() => navigate(crumb.href!)}
                    className="text-text-secondary hover:text-text transition-colors"
                  >
                    {crumb.label}
                  </button>
                ) : (
                  <span className="text-text font-medium truncate">{crumb.label}</span>
                )}
              </span>
            ))}
          </nav>
        ) : (
          <h1 className="text-lg font-semibold text-text truncate">{title}</h1>
        )}
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
        {/* Vocabulary toggle */}
        {isFeatureEnabled('header.beleid_architectuur_toggle') && (
        <div className="hidden sm:flex items-center h-9 rounded-xl border border-border text-xs overflow-hidden">
          {(Object.keys(VOCABULARY_LABELS) as VocabularyId[]).map((id) => (
            <button
              key={id}
              onClick={() => setVocabularyId(id)}
              className={`h-full px-2.5 transition-colors ${
                vocabularyId === id
                  ? 'bg-primary-100 text-primary-700 font-medium'
                  : 'text-text-secondary hover:text-text hover:bg-gray-50'
              }`}
            >
              {VOCABULARY_LABELS[id]}
            </button>
          ))}
        </div>
        )}

        {/* Admin view-as-non-admin toggle */}
        {realIsAdmin && (
          <button
            onClick={toggleViewAsNonAdmin}
            className={`flex items-center justify-center h-7 w-7 rounded-lg transition-all ${
              viewAsNonAdmin
                ? 'bg-amber-100 text-amber-700 border border-amber-300'
                : 'text-text-secondary hover:text-text hover:bg-gray-100'
            }`}
            title={viewAsNonAdmin ? 'Terug naar beheerweergave' : 'Bekijk als medewerker'}
          >
            {viewAsNonAdmin ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        )}

        {/* Notification bell */}
        <NotificationBell />

        {/* Search shortcut */}
        <button
          onClick={() => useUIStore.getState().setSearchModalOpen(true)}
          className="flex items-center justify-center gap-2 h-9 px-2.5 sm:px-3 rounded-xl border border-border text-sm text-text-secondary hover:border-border-hover hover:text-text transition-all"
        >
          <Search className="h-4 w-4" />
          <span className="hidden sm:inline">Zoeken...</span>
          <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-gray-100 text-[10px] font-medium text-text-secondary">
            /
          </kbd>
        </button>

        {/* Dev-mode person picker (only when OIDC is not configured) */}
        {!oidcConfigured ? (
          <div className="relative" ref={pickerRef}>
            <button
              onClick={() => setShowDevPicker(!showDevPicker)}
              className="flex items-center gap-1.5 h-9 px-2 rounded-xl border border-border hover:border-border-hover transition-all"
            >
              <div className="flex items-center justify-center h-6 w-6 rounded-full bg-primary-100 text-primary-700 text-[11px] font-medium">
                {initials || <User className="h-3.5 w-3.5" />}
              </div>
              {currentPerson && (
                <span className="text-sm text-text hidden sm:inline max-w-[120px] truncate">
                  {currentPerson.naam}
                </span>
              )}
              <ChevronDown className="h-3.5 w-3.5 text-text-secondary" />
            </button>

            {showDevPicker && (
              <div className="absolute right-0 top-full mt-1 w-72 bg-white border border-border rounded-xl shadow-lg z-50 overflow-hidden">
                <div className="p-2 border-b border-border">
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Zoek persoon..."
                    className="w-full px-3 py-1.5 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
                    autoFocus
                  />
                </div>
                <div className="max-h-64 overflow-y-auto py-1">
                  {filteredPeople.map((person) => (
                    <button
                      key={person.id}
                      onClick={() => {
                        setDevPersonId(person.id);
                        setShowDevPicker(false);
                        setSearch('');
                      }}
                      className="flex items-center gap-3 w-full px-3 py-2 text-left hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-center justify-center h-7 w-7 rounded-full bg-primary-100 text-primary-700 text-xs font-medium shrink-0">
                        {getInitials(person.naam)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-text truncate">{person.naam}</p>
                        {person.functie && (
                          <p className="text-xs text-text-secondary truncate">{formatFunctie(person.functie)}</p>
                        )}
                      </div>
                      {currentPerson?.id === person.id && (
                        <Check className="h-4 w-4 text-primary-600 shrink-0" />
                      )}
                    </button>
                  ))}
                  {filteredPeople.length === 0 && (
                    <p className="px-3 py-2 text-sm text-text-secondary">Geen resultaten</p>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-1.5 h-9 px-2 rounded-xl border border-border">
            <div className="flex items-center justify-center h-6 w-6 rounded-full bg-primary-100 text-primary-700 text-[11px] font-medium">
              {initials || <User className="h-3.5 w-3.5" />}
            </div>
            {currentPerson && (
              <span className="text-sm text-text hidden sm:inline max-w-[120px] truncate">
                {currentPerson.naam}
              </span>
            )}
          </div>
        )}

        {/* Logout button */}
        {authenticated && (
          <button
            onClick={logout}
            className="flex items-center justify-center gap-1.5 h-9 px-2.5 rounded-xl border border-border text-sm text-text-secondary hover:border-border-hover hover:text-text transition-all"
            title="Uitloggen"
          >
            <LogOut className="h-4 w-4" />
            <span className="hidden sm:inline">Uitloggen</span>
          </button>
        )}
      </div>
    </header>
  );
}
