import { useRef, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { NlddButton } from '@/components/nldd/NlddLink';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { useNlddEvent, useNlddValue, eventValue } from '@/components/nldd/events';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { useAuth } from '@/contexts/AuthContext';
import { VOCABULARY_LABELS, type VocabularyId } from '@/vocabulary';
import { NotificationBell } from '@/components/common/NotificationBell';
import { useManagedEenheden } from '@/hooks/useOrganisatie';
import { formatOrganisatieType, formatFunctie, type Person } from '@/types';
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

/** The vocabulary choice, as one control rather than a row of buttons. */
function VocabularySwitch({
  value,
  onChange,
}: {
  value: VocabularyId;
  onChange: (id: VocabularyId) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddValue(ref, value);
  useNlddEvent(ref, 'change', (e) => onChange(eventValue(e) as VocabularyId));
  return (
    <nldd-segmented-control ref={ref} type="radio" size="sm" value={value} accessible-label="Woordenlijst">
      {(Object.keys(VOCABULARY_LABELS) as VocabularyId[]).map((id) => (
        <nldd-segmented-control-item key={id} value={id} text={VOCABULARY_LABELS[id]} />
      ))}
    </nldd-segmented-control>
  );
}

/**
 * Local-development person switcher, shown only when OIDC is not configured.
 *
 * An nldd-combo-box: it is a list you filter by typing, which is what the
 * hand-built version was doing with its own text input, its own filter and its
 * own mousedown listener on document to close again.
 */
function DevPersonPicker({
  people,
  currentPerson,
  onPick,
}: {
  people: Person[];
  currentPerson: Person | null | undefined;
  onPick: (id: string) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddValue(ref, currentPerson?.id ?? '');
  useNlddEvent(ref, 'change', (e) => {
    const id = eventValue(e);
    if (id) onPick(id);
  });
  return (
    <nldd-container width="fit-content" style={{ minWidth: '180px' }}>
      <nldd-combo-box
        ref={ref}
        value={currentPerson?.id ?? ''}
        placeholder="Kies persoon"
        accessible-label="Persoon kiezen (ontwikkelmodus)"
      >
        <nldd-menu>
          {people.map((person) => (
            <nldd-menu-item
              key={person.id}
              value={person.id}
              text={person.naam}
              {...(person.functie ? { details: formatFunctie(person.functie) } : {})}
            />
          ))}
        </nldd-menu>
      </nldd-combo-box>
    </nldd-container>
  );
}

export function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const { currentPerson, setDevPersonId, people } = useCurrentPerson();
  const { vocabularyId, setVocabularyId } = useVocabulary();
  const { authenticated, oidcConfigured, logout, realIsAdmin, viewAsNonAdmin, toggleViewAsNonAdmin } = useAuth();
  const toggleMobileSidebar = useUIStore((s) => s.toggleMobileSidebar);

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
      <nldd-container slot="toolbar" layout="row" gap="8" vertical-alignment="center" width="fit-content">
        {/* Only shown while the sidebar is a sheet; above lg the pane is visible. */}
        <nldd-container width="fit-content" hide-above="lg">
          <NlddIconButton
            icon="menu"
            accessibleLabel="Navigatie openen"
            onClick={toggleMobileSidebar}
          />
        </nldd-container>
        {/* Vocabulary toggle. A segmented control rather than a row of buttons:
            it is one choice out of a set, so the items are radios and the
            arrow keys move between them. */}
        <nldd-container width="fit-content" hide-below="sm">
          <VocabularySwitch value={vocabularyId} onChange={setVocabularyId} />
        </nldd-container>

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
          <DevPersonPicker
            people={people}
            currentPerson={currentPerson}
            onPick={setDevPersonId}
          />
        ) : (
          <nldd-container layout="row" gap="8" vertical-alignment="center" width="fit-content">
            <nldd-avatar
              size="24"
              {...(currentPerson ? { name: currentPerson.naam } : { icon: 'person' })}
              decorative
            />
            {currentPerson && (
              <nldd-container width="fit-content" hide-below="sm">
                <nldd-text size="sm">{currentPerson.naam}</nldd-text>
              </nldd-container>
            )}
          </nldd-container>
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
      </nldd-container>
    </nldd-top-title-bar>
  );
}
