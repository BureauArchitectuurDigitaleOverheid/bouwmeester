import { useState, useEffect } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { WhitelistManager } from '@/components/admin/WhitelistManager';
import { UserManager } from '@/components/admin/UserManager';
import { DatabaseBackup } from '@/components/admin/DatabaseBackup';
import { AccessRequestManager } from '@/components/admin/AccessRequestManager';
import { PlacementRequestManager } from '@/components/admin/PlacementRequestManager';
import { ConfigManager } from '@/components/admin/ConfigManager';
import { EdgeSchemaManager } from '@/components/admin/EdgeSchemaManager';
import { FeatureTogglesContent } from '@/pages/FeatureTogglesPage';

type Tab = 'whitelist' | 'users' | 'database' | 'requests' | 'placements' | 'config' | 'schema' | 'features';

const ALL_TABS = ['whitelist', 'users', 'database', 'requests', 'placements', 'config', 'schema', 'features'] as const;

export function AdminPage() {
  const { person, oidcConfigured, loading, viewAsNonAdmin } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as Tab | null;

  const isAdmin = person?.is_admin ?? false;
  const isManager = (person?.managed_eenheden?.length ?? 0) > 0;

  // Managers who are not admins default to the placements tab
  const defaultTab: Tab = isAdmin ? 'whitelist' : 'placements';
  const [activeTab, setActiveTab] = useState<Tab>(tabParam || defaultTab);

  // Sync tab from URL param
  useEffect(() => {
    if (tabParam && (ALL_TABS as readonly string[]).includes(tabParam)) {
      setActiveTab(tabParam);
    }
  }, [tabParam]);

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    setSearchParams(tab === defaultTab ? {} : { tab });
  };

  // While loading auth, show nothing (prevents flash of admin UI)
  if (loading) {
    return null;
  }

  // Redirect users who are neither admin nor manager (or admins in view-as-non-admin mode)
  if (viewAsNonAdmin || (oidcConfigured && (!person || (!isAdmin && !isManager)))) {
    return <Navigate to="/" replace />;
  }

  // Admins see all tabs, managers only see placements
  const adminTabs: { id: Tab; label: string }[] = [
    { id: 'whitelist', label: 'Toegangslijst' },
    { id: 'requests', label: 'Verzoeken' },
    { id: 'placements', label: 'Plaatsingsverzoeken' },
    { id: 'users', label: 'Gebruikers' },
    { id: 'config', label: 'Omgevingsvariabelen' },
    { id: 'features', label: 'Functionaliteit' },
    { id: 'schema', label: 'Relatieschema' },
    { id: 'database', label: 'Database' },
  ];

  const managerTabs: { id: Tab; label: string }[] = [
    { id: 'placements', label: 'Plaatsingsverzoeken' },
  ];

  const tabs = isAdmin ? adminTabs : managerTabs;

  return (
    <div className="max-w-4xl">
      {/* Tab bar */}
      <div className="flex border-b border-border mb-6 overflow-x-auto scrollbar-hide -mx-4 px-4 md:-mx-6 md:px-6">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap shrink-0 ${
              activeTab === tab.id
                ? 'border-primary-600 text-primary-700'
                : 'border-transparent text-text-secondary hover:text-text hover:border-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'whitelist' && isAdmin && <WhitelistManager />}
      {activeTab === 'requests' && isAdmin && <AccessRequestManager />}
      {activeTab === 'placements' && <PlacementRequestManager />}
      {activeTab === 'users' && isAdmin && <UserManager />}
      {activeTab === 'database' && isAdmin && <DatabaseBackup />}
      {activeTab === 'config' && isAdmin && <ConfigManager />}
      {activeTab === 'features' && isAdmin && <FeatureTogglesContent />}
      {activeTab === 'schema' && isAdmin && <EdgeSchemaManager />}
    </div>
  );
}
