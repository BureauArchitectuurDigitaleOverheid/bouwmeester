import { useState, useRef, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Search, User, ChevronDown, Check, LogOut, Eye, X } from 'lucide-react';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { useAuth } from '@/contexts/AuthContext';
import { VOCABULARY_LABELS, type VocabularyId } from '@/vocabulary';
import { NotificationBell } from '@/components/common/NotificationBell';
import { useManagedEenheden } from '@/hooks/useOrganisatie';
import { ORGANISATIE_TYPE_LABELS, formatFunctie } from '@/types';

const pageTitles: Record<string, string> = {
  '/': 'Inbox',
  '/corpus': 'Corpus',
  '/tasks': 'Taken',
  '/people': 'Personen',
  '/organisatie': 'Organisatie',
  '/parlementair': 'Kamerstukken',
  '/auditlog': 'Auditlog',
  '/search': 'Zoeken',
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
  const { currentPerson, setCurrentPersonId, people, isViewingAsOther, resetToSelf } =
    useCurrentPerson();
  const { vocabularyId, setVocabularyId } = useVocabulary();
  const { authenticated, oidcConfigured, person: authPerson, logout } = useAuth();
  const [showPersonPicker, setShowPersonPicker] = useState(false);
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
    if (!showPersonPicker) return;
    const handleClick = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowPersonPicker(false);
        setSearch('');
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showPersonPicker]);

  const filteredPeople = people.filter((p) =>
    p.naam.toLowerCase().includes(search.toLowerCase()),
  );

  const initials = currentPerson ? getInitials(currentPerson.naam) : null;

  // In SSO mode, determine the authenticated user's display name
  const authDisplayName = oidcConfigured ? (authPerson?.name || authPerson?.email || '') : '';

  return (
    <header className="flex items-center justify-between h-16 px-6 bg-surface border-b border-border shrink-0">
      {/* Left: Title / Breadcrumbs */}
      <div className="flex items-center gap-2">
        {breadcrumbs ? (
          <nav className="flex items-center gap-1.5 text-sm">
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
                  <span className="text-text font-medium">{crumb.label}</span>
                )}
              </span>
            ))}
          </nav>
        ) : (
          <h1 className="text-lg font-semibold text-text">{title}</h1>
        )}
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-3">
        {/* Vocabulary toggle */}
        <div className="flex items-center rounded-lg border border-border text-xs overflow-hidden">
          {(Object.keys(VOCABULARY_LABELS) as VocabularyId[]).map((id) => (
            <button
              key={id}
              onClick={() => setVocabularyId(id)}
              className={`px-2.5 py-1.5 transition-colors ${
                vocabularyId === id
                  ? 'bg-primary-100 text-primary-700 font-medium'
                  : 'text-text-secondary hover:text-text hover:bg-gray-50'
              }`}
            >
              {VOCABULARY_LABELS[id]}
            </button>
          ))}
        </div>

        {/* Notification bell */}
        <NotificationBell personId={currentPerson?.id} />

        {/* Search shortcut */}
        <button
          onClick={() => navigate('/search')}
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border text-sm text-text-secondary hover:border-border-hover hover:text-text transition-all"
        >
          <Search className="h-4 w-4" />
          <span className="hidden sm:inline">Zoeken...</span>
          <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-gray-100 text-[10px] font-medium text-text-secondary">
            /
          </kbd>
        </button>

        {/* "Viewing as" indicator (SSO mode only) */}
        {isViewingAsOther && (
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-700">
            <Eye className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Bekijk als {currentPerson?.naam}</span>
            <button
              onClick={resetToSelf}
              className="ml-0.5 p-0.5 rounded hover:bg-amber-100 transition-colors"
              title="Terug naar eigen profiel"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )}

        {/* Person picker */}
        <div className="relative" ref={pickerRef}>
          <button
            onClick={() => setShowPersonPicker(!showPersonPicker)}
            className="flex items-center gap-2 px-2 py-1.5 rounded-xl border border-border hover:border-border-hover transition-all"
          >
            <div className="flex items-center justify-center h-7 w-7 rounded-full bg-primary-100 text-primary-700 text-xs font-medium">
              {initials || <User className="h-3.5 w-3.5" />}
            </div>
            {currentPerson && (
              <span className="text-sm text-text hidden sm:inline max-w-[120px] truncate">
                {currentPerson.naam}
              </span>
            )}
            <ChevronDown className="h-3.5 w-3.5 text-text-secondary" />
          </button>

          {showPersonPicker && (
            <div className="absolute right-0 top-full mt-1 w-72 bg-white border border-border rounded-xl shadow-lg z-50 overflow-hidden">
              {/* SSO mode label */}
              {oidcConfigured && authDisplayName && (
                <div className="px-3 py-2 bg-gray-50 border-b border-border">
                  <p className="text-xs text-text-secondary">Ingelogd als</p>
                  <p className="text-sm text-text font-medium truncate">{authDisplayName}</p>
                </div>
              )}
              <div className="p-2 border-b border-border">
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={oidcConfigured ? 'Bekijk als...' : 'Zoek persoon...'}
                  className="w-full px-3 py-1.5 text-sm rounded-lg border border-border focus:outline-none focus:border-primary-400"
                  autoFocus
                />
              </div>
              <div className="max-h-64 overflow-y-auto py-1">
                {filteredPeople.map((person) => (
                  <button
                    key={person.id}
                    onClick={() => {
                      setCurrentPersonId(person.id);
                      setShowPersonPicker(false);
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

        {/* Logout button */}
        {authenticated && (
          <button
            onClick={logout}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border border-border text-sm text-text-secondary hover:border-border-hover hover:text-text transition-all"
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
