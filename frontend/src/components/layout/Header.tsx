import { useState, useRef, useEffect, useCallback, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { NlddButton } from '@/components/nldd/NlddLink';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { useNlddEvent, useNlddValue, eventValue, orUndef } from '@/components/nldd/events';
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
  // A node detail page lives under Corpus. Without an entry the bar fell back
  // to "Bouwmeester", which named the app rather than the page and left the
  // route's only real title to an h2 in the body.
  '/nodes': 'Corpus',
};

/**
 * Breakpoint helpers.
 *
 * nldd-container has no responsive visibility: `hide-above` / `hide-below` are
 * attributes of the CELL components, and on a container they are silently
 * ignored, which is how three of these ended up doing nothing. A matchMedia
 * hook is honest about being app-level logic rather than pretending the
 * container supports it.
 */
function useWiderThan(px: number): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(`(min-width: ${px}px)`).matches);
  useEffect(() => {
    const mq = window.matchMedia(`(min-width: ${px}px)`);
    const onChange = () => setMatches(mq.matches);
    mq.addEventListener('change', onChange);
    setMatches(mq.matches);
    return () => mq.removeEventListener('change', onChange);
  }, [px]);
  return matches;
}

function ShowAbove({ width, slot, children }: { width: number; slot?: string; children: ReactNode }) {
  if (!useWiderThan(width)) return null;
  return slot ? <span slot={slot}>{children}</span> : <>{children}</>;
}

function ShowBelow({ width, slot, children }: { width: number; slot?: string; children: ReactNode }) {
  if (useWiderThan(width)) return null;
  return slot ? <span slot={slot}>{children}</span> : <>{children}</>;
}

/**
 * The admin's "view as a regular member" switch.
 *
 * `type="button"` rather than a checkbox: it is announced with aria-pressed,
 * which is what a mode you turn on and off wants.
 */
function ViewAsToggle({ active, onToggle }: { active: boolean; onToggle: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', onToggle);
  return (
    <nldd-toggle-button
      ref={ref}
      type="button"
      size="sm"
      icon={active ? 'eye-slash' : 'eye'}
      selected={orUndef(active)}
      accessible-label={active ? 'Terug naar beheerweergave' : 'Bekijk als medewerker'}
    />
  );
}

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
    <nldd-segmented-control
      ref={ref}
      type="radio"
      size="sm"
      value={value}
      accessible-label="Woordenlijst"
      className="keep-label-width"
    >
      {(Object.keys(VOCABULARY_LABELS) as VocabularyId[]).map((id) => (
        <nldd-segmented-control-item key={id} value={id} text={VOCABULARY_LABELS[id]} />
      ))}
    </nldd-segmented-control>
  );
}

/**
 * Local-development person switcher, shown only when OIDC is not configured.
 *
 * A list you filter by typing, which the design system models directly; no
 * text input, filter and document mousedown listener of our own.
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
  // nldd-dropdown, not nldd-combo-box. The combo-box is "a text input with
  // autocomplete": it shows the chosen value as editable, spell-checked text
  // with a clear button beside it. Picking one of a fixed list of people is a
  // select, and the dropdown wraps a native one, so the browser keeps the
  // keyboard handling and the accessibility.
  //
  // The listener sits on the DROPDOWN, not on the slotted <select>. React's
  // onChange does not fire there: its synthetic event system never reaches a
  // native control slotted into a custom element. The dropdown re-emits the
  // change itself, with the value in `detail`.
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'change', (event) => {
    const value =
      (event as CustomEvent<{ value?: string }>).detail?.value ??
      (event.target as HTMLSelectElement | null)?.value;
    if (value) onPick(value);
  });

  // The selected person is mirrored onto the <select> rather than passed as
  // `defaultValue`. `people` arrives from a query, so on the first render the
  // list is empty and a default freezes on "" — after a reload the header read
  // "Kies persoon" while the app was signed in as someone. Assigning `value`
  // once the matching <option> exists is what makes it stick.
  const selectRef = useRef<HTMLSelectElement>(null);
  const currentPersonId = currentPerson?.id ?? '';
  useEffect(() => {
    const select = selectRef.current;
    if (select && select.value !== currentPersonId) {
      select.value = currentPersonId;
    }
  }, [currentPersonId, people]);

  return (
    <nldd-dropdown
      ref={ref}
      accessible-label="Persoon kiezen (ontwikkelmodus)"
      width="200px"
    >
      <select ref={selectRef}>
        <option value="" disabled>
          Kies persoon
        </option>
        {people.map((person) => (
          <option key={person.id} value={person.id}>
            {person.naam}
            {person.functie ? ` — ${formatFunctie(person.functie)}` : ''}
          </option>
        ))}
      </select>
    </nldd-dropdown>
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
    // The bar renders the h1 itself and, on a detail page, the back
    // affordance.
    <nldd-top-title-bar
      ref={barRef}
      text={title}
      {...(breadcrumbs ? { 'back-text': 'Corpus' } : {})}
    >
      <>
        {/* Only shown while the sidebar is a sheet; above lg the pane is visible. */}
        <ShowBelow width={1024} slot="toolbar">
          <NlddIconButton
            icon="menu"
            accessibleLabel="Navigatie openen"
            onClick={toggleMobileSidebar}
          />
        </ShowBelow>
        {/* Vocabulary toggle. A segmented control rather than a row of buttons:
            it is one choice out of a set, so the items are radios and the
            arrow keys move between them. */}
        <ShowAbove width={640} slot="toolbar">
          <VocabularySwitch value={vocabularyId} onChange={setVocabularyId} />
        </ShowAbove>

        {/* Admin view-as-non-admin toggle.

            A toggle button, not an icon button that swaps its own variant:
            this is a state you are in, not an action you fire. The element
            carries aria-pressed and draws both states itself, so it reads as a
            control in either one. As an icon button it was transparent while
            off, which left a bare icon with no button shape at all. */}
        {realIsAdmin && (
          <span slot="toolbar">
            <ViewAsToggle active={viewAsNonAdmin} onToggle={toggleViewAsNonAdmin} />
          </span>
        )}

        {/* Notification bell */}
        <span slot="toolbar"><NotificationBell /></span>

        {/* Search. An icon button like the other toolbar actions: a labelled
            button here competed with the page title and the profile picker for
            the same row, and the magnifier is the one icon nobody has to
            learn. The shortcut stays in the accessible name. */}
        <span slot="toolbar">
          <NlddIconButton
            icon="magnifier"
            accessibleLabel="Zoeken (sneltoets /)"
            onClick={() => {
              // On the search page itself, focus the field that is already
              // there rather than stacking a modal on top of it: two search
              // boxes on one screen, each with its own results. The `/`
              // shortcut in AppLayout makes the same distinction.
              if (location.pathname === '/search') {
                document.querySelector<HTMLElement & { focus?: () => void }>(
                  'nldd-search-field',
                )?.focus?.();
                return;
              }
              useUIStore.getState().setSearchModalOpen(true);
            }}
          />
        </span>

        {/* Dev-mode person picker (only when OIDC is not configured) */}
        {!oidcConfigured ? (
          <span slot="toolbar">
            <DevPersonPicker
              people={people}
              currentPerson={currentPerson}
              onPick={setDevPersonId}
            />
          </span>
        ) : (
          <nldd-container slot="toolbar" layout="row" gap="8" vertical-alignment="center">
            <nldd-avatar
              size="24"
              {...(currentPerson ? { name: currentPerson.naam } : { icon: 'person' })}
              decorative
            />
            {currentPerson && (
              <ShowAbove width={640}>
                <nldd-text size="sm">{currentPerson.naam}</nldd-text>
              </ShowAbove>
            )}
          </nldd-container>
        )}

        {/* Logout button */}
        {authenticated && (
          <span slot="toolbar">
            <NlddButton
              variant="neutral-base"
              size="sm"
              startIcon="logout"
              text="Uitloggen"
              onClick={logout}
            />
          </span>
        )}
      </>
    </nldd-top-title-bar>
  );
}
