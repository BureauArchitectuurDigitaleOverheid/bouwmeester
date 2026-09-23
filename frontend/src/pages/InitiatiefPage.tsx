import { useCallback, useRef } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useNlddEvent } from '@/components/nldd/events';
import { useInitiatief } from '@/hooks/useInitiatieven';
import { initiatiefIconColor } from '@/components/initiatieven/initiatiefColors';
import { InitiatiefLeads } from '@/components/initiatieven/InitiatiefLeads';
import { InitiatiefUpdates } from '@/components/initiatieven/InitiatiefUpdates';
import { InitiatiefMensen } from '@/components/initiatieven/InitiatiefMensen';
import { InitiatiefSignalen } from '@/components/initiatieven/InitiatiefSignalen';
import { InitiatiefInstellingen } from '@/components/initiatieven/InitiatiefInstellingen';
import {
  initiatiefPath,
  isInitiatiefTab,
  type InitiatiefTab,
} from '@/utils/initiatiefRoutes';
import type { InitiatiefDetail } from '@/types';
import { richTextToPlain } from '@/utils/richtext';

const TAB_LABELS: Record<InitiatiefTab, string> = {
  leads: 'Leads',
  updates: 'Updates',
  mensen: 'Mensen',
  signalen: 'Signalen',
  instellingen: 'Instellingen',
};

/**
 * The tabs this person gets. Ordered by how often they are used: the leads
 * daily, updates weekly, people and signals now and then, settings once.
 * A viewer changes nothing, so has no settings tab.
 */
function visibleTabs(initiatief: InitiatiefDetail): InitiatiefTab[] {
  const canEdit =
    initiatief.access_level === 'eigenaar' || initiatief.access_level === 'contributor';
  const tabs: InitiatiefTab[] = ['leads', 'updates', 'mensen', 'signalen'];
  if (canEdit) tabs.push('instellingen');
  return tabs;
}

/**
 * One initiatief, with its work split over tabs. This replaces the settings
 * modal on the old leads page, which had grown to hold everything but the
 * leads themselves. The tab is part of the path, so each one can be linked.
 */
export function InitiatiefPage() {
  const { id, tab } = useParams<{ id: string; tab?: string }>();
  const navigate = useNavigate();
  const { data: initiatief, isLoading, isError } = useInitiatief(id);

  const tabBarRef = useRef<HTMLElement>(null);
  const handleTabChange = useCallback(
    (event: Event) => {
      const item = (event as CustomEvent<{ item?: HTMLElement }>).detail?.item;
      const next = item?.dataset.tabId;
      if (id && isInitiatiefTab(next)) navigate(initiatiefPath(id, next));
    },
    [id, navigate],
  );
  useNlddEvent(tabBarRef, 'tabchange', handleTabChange);

  if (isLoading) {
    return (
      <nldd-container layout="row" horizontal-alignment="center" padding="48">
        <LoadingSpinner />
      </nldd-container>
    );
  }
  if (!id || isError || !initiatief) {
    return (
      <nldd-container padding="48" horizontal-alignment="center">
        <nldd-text size="sm" color="secondary" horizontal-alignment="center">
          Initiatief niet gevonden, of je hebt er geen toegang toe.
        </nldd-text>
      </nldd-container>
    );
  }

  const tabs = visibleTabs(initiatief);
  const activeTab: InitiatiefTab | null = tab === undefined ? 'leads' : isInitiatiefTab(tab) ? tab : null;
  if (!activeTab || !tabs.includes(activeTab)) {
    return <Navigate to={initiatiefPath(id)} replace />;
  }

  // Three levels, each set off from the next: who (name and description),
  // where (the tabs), and what (the tab's own tools and content).
  return (
    <nldd-container gap="24">
      <nldd-container gap="16">
        <nldd-container gap="4">
          <nldd-container layout="row" gap="8" vertical-alignment="center">
            <nldd-icon
              name="circle-filled"
              size="16"
              color={initiatiefIconColor(initiatief.kleur)}
              aria-hidden="true"
            />
            <nldd-title size={3}>
              <h2>{initiatief.naam}</h2>
            </nldd-title>
            {initiatief.public_page_enabled && initiatief.slug && (
              <nldd-link
                href={`/c/${initiatief.slug}`}
                target="_blank"
                size="xs"
                start-icon="globe"
                text={`/c/${initiatief.slug}`}
              />
            )}
          </nldd-container>
          {/* One plain line under the name. The rendered rich text brought
              paragraph margins that set it apart from its own heading. */}
          {initiatief.beschrijving && (
            <nldd-text size="sm" color="secondary">
              {richTextToPlain(initiatief.beschrijving)}
            </nldd-text>
          )}
        </nldd-container>

        <nldd-tab-bar ref={tabBarRef} variant="text" accessible-label="Onderdelen van het initiatief">
          {tabs.map((t) => (
            <nldd-tab-bar-item
              key={t}
              text={TAB_LABELS[t]}
              data-tab-id={t}
              current={activeTab === t ? true : undefined}
            />
          ))}
        </nldd-tab-bar>
      </nldd-container>

      {/* Keyed on the initiatief, so switching between two of them does not
          carry a half-typed form or a filter from one into the other. */}
      <div key={initiatief.id}>
        {activeTab === 'leads' && <InitiatiefLeads initiatiefId={initiatief.id} />}
        {activeTab === 'updates' && <TabBody><InitiatiefUpdates initiatief={initiatief} /></TabBody>}
        {activeTab === 'mensen' && <TabBody><InitiatiefMensen initiatief={initiatief} /></TabBody>}
        {activeTab === 'signalen' && <TabBody><InitiatiefSignalen initiatief={initiatief} /></TabBody>}
        {activeTab === 'instellingen' && <TabBody><InitiatiefInstellingen initiatief={initiatief} /></TabBody>}
      </div>
    </nldd-container>
  );
}

/**
 * The leads need the full width for the board; the other tabs are forms and
 * lists, which read badly stretched across a wide screen.
 */
function TabBody({ children }: { children: React.ReactNode }) {
  return (
    <nldd-container max-width="768px" padding-top="8">
      {children}
    </nldd-container>
  );
}
