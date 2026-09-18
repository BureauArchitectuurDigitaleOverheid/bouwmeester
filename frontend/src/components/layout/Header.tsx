import { useState, useRef, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Icon } from '@/components/nldd/Icon';
import { NlddButton } from '@/components/nldd/NlddLink';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { useNlddEvent } from '@/components/nldd/events';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { useAuth } from '@/contexts/AuthContext';
import { VOCABULARY_LABELS, type VocabularyId } from '@/vocabulary';
import { NotificationBell } from '@/components/common/NotificationBell';
import { useManagedEenheden } from '@/hooks/useOrganisatie';
import { formatOrganisatieType, formatFunctie } from '@/types';
import { useUIStore } from '@/store/ui';

const pageTitles: Record<string, string> = {
  '/': 'Inbox',
  '/corpus': 'Corpus',
  '/tasks': 'Taken',
  '/people': 'Personen',
  '/organisatie': 'Organisatie',
  '/parlementair': 'Kamerstukken',
  '/opdrachten': 'Opdrachten & Subsidies',
  '/admin': 'Beheer',
  '/instellingen': 'Instellingen',
  '/auditlog': 'Auditlog',
  '/search': 'Zoeken',
  '/docs': 'Handleiding',
  '/leads': 'Leads',
  '/samenwerkingsverbanden': 'Samenwerkingsverbanden',
  '/share-target': 'Nieuwe lead',
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

  // Dev-mode person picker state (only used when !oidcConfigured)
  const [showDevPicker, setShowDevPicker] = useState(false);
  const [search, setSearch] = useState('');
  const pickerRef = useRef<HTMLDivElement>(null);

  const { data: managedEenheden } = useManagedEenheden(currentPerson?.id);

  const pathBase = '/' + (location.pathname.split('/')[1] || '');
  const eenheidTitle = (() => {
    const first = managedEenheden?.[0];
    if (first) {
      const label = formatOrganisatieType(first.type);
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

  // `back-href` would trigger a full page load, so the bar fires `back` instead
  // and the router handles it. Bound here only: the event bubbles, and binding
  // it on an ancestor as well would run the handler twice for one press.
  const barRef = useRef<HTMLElement>(null);
  const handleBack = useCallback(() => navigate('/corpus'), [navigate]);
  useNlddEvent(barRef, 'back', breadcrumbs ? handleBack : undefined);

  return (
    // The bar renders the h1 itself and, on a detail page, the back affordance
    // that used to be a hand-rolled breadcrumb trail.
    <nldd-top-title-bar
      ref={barRef}
      text={title}
      {...(breadcrumbs ? { 'back-text': 'Corpus' } : {})}
    >
      <div slot="toolbar" className="flex shrink-0 items-center gap-1.5 sm:gap-2">
        {/* Only shown while the sidebar is a sheet; above lg the pane is visible. */}
        <span className="lg:hidden">
          <NlddIconButton
            icon="menu"
            accessibleLabel="Navigatie openen"
            onClick={toggleMobileSidebar}
          />
        </span>
        {/* Vocabulary toggle */}
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

        {/* Admin view-as-non-admin toggle */}
        {realIsAdmin && (
          <NlddIconButton
            icon={viewAsNonAdmin ? 'eye-slash' : 'eye'}
            variant={viewAsNonAdmin ? 'neutral-tinted' : 'neutral-transparent'}
            size="sm"
            accessibleLabel={
              viewAsNonAdmin ? 'Terug naar beheerweergave' : 'Bekijk als medewerker'
            }
            onClick={toggleViewAsNonAdmin}
          />
        )}

        {/* Notification bell */}
        <NotificationBell />

        {/* Search shortcut */}
        <NlddButton
          variant="neutral-base"
          size="sm"
          startIcon="magnifier"
          text="Zoeken"
          accessibleLabel="Zoeken (sneltoets /)"
          onClick={() => useUIStore.getState().setSearchModalOpen(true)}
        />

        {/* Dev-mode person picker (only when OIDC is not configured) */}
        {!oidcConfigured ? (
          <div className="relative" ref={pickerRef}>
            <button
              onClick={() => setShowDevPicker(!showDevPicker)}
              className="flex items-center gap-1.5 h-9 px-2 rounded-xl border border-border hover:border-border-hover transition-all"
            >
              <div className="flex items-center justify-center h-6 w-6 rounded-full bg-primary-100 text-primary-700 text-[11px] font-medium">
                {initials || <Icon name="person" size="sm" />}
              </div>
              {currentPerson && (
                <span className="text-sm text-text hidden sm:inline max-w-[120px] truncate">
                  {currentPerson.naam}
                </span>
              )}
              <Icon name="chevron-down" size="sm" className="text-text-secondary" />
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
                        <Icon name="check-mark" className="shrink-0 text-primary-600" />
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
              {initials || <Icon name="person" size="sm" />}
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
          <NlddButton
            variant="neutral-base"
            size="sm"
            startIcon="logout"
            text="Uitloggen"
            onClick={logout}
          />
        )}
      </div>
    </nldd-top-title-bar>
  );
}
