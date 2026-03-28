import { useState, useEffect } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { usePermissions } from '@/hooks/usePermissions';
import { WhitelistManager } from '@/components/admin/WhitelistManager';
import { DatabaseBackup } from '@/components/admin/DatabaseBackup';
import { AccessRequestManager } from '@/components/admin/AccessRequestManager';
import { PlacementRequestManager } from '@/components/admin/PlacementRequestManager';
import { ConfigManager } from '@/components/admin/ConfigManager';
import { EdgeSchemaManager } from '@/components/admin/EdgeSchemaManager';
import { SharingManager } from '@/components/admin/SharingManager';
import { RoleManager } from '@/components/admin/RoleManager';

type Tab =
  | 'whitelist'
  | 'database'
  | 'requests'
  | 'placements'
  | 'config'
  | 'schema'
  | 'users'
  | 'sharing';

export function AdminPage() {
  const { person, oidcConfigured, loading, viewAsNonAdmin } = useAuth();
  const { hasPermission, hasAnyPermission } = usePermissions();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as Tab | null;

  const isManager = (person?.managed_eenheden?.length ?? 0) > 0;
  const canAdmin = hasAnyPermission(
    'whitelist:manage',
    'people:manage',
    'config:manage',
    'database:backup',
    'people:assign_role',
    'org:manage',
  );

  const defaultTab: Tab = canAdmin ? 'whitelist' : 'placements';
  const [activeTab, setActiveTab] = useState<Tab>(tabParam || defaultTab);

  useEffect(() => {
    if (tabParam) {
      setActiveTab(tabParam);
    }
  }, [tabParam]);

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    setSearchParams(tab === defaultTab ? {} : { tab });
  };

  if (loading) {
    return null;
  }

  if (viewAsNonAdmin || (oidcConfigured && (!person || (!canAdmin && !isManager)))) {
    return <Navigate to="/" replace />;
  }

  // Build tabs based on permissions
  const tabs: { id: Tab; label: string }[] = [];

  if (hasPermission('whitelist:manage')) {
    tabs.push({ id: 'whitelist', label: 'Toegangslijst' });
    tabs.push({ id: 'requests', label: 'Verzoeken' });
  }
  if (hasPermission('people:manage') || isManager) {
    tabs.push({ id: 'placements', label: 'Plaatsingsverzoeken' });
  }
  if (hasPermission('people:assign_role')) {
    tabs.push({ id: 'users', label: 'Gebruikers' });
  }
  if (hasPermission('org:manage')) {
    tabs.push({ id: 'sharing', label: 'Delen' });
  }
  if (hasPermission('config:manage')) {
    tabs.push({ id: 'config', label: 'Omgevingsvariabelen' });
    tabs.push({ id: 'schema', label: 'Relatieschema' });
  }
  if (hasPermission('database:backup')) {
    tabs.push({ id: 'database', label: 'Database' });
  }

  return (
    <div className="max-w-6xl">
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

      {/* Tab content — only render if the tab is in the visible set */}
      {tabs.some((t) => t.id === activeTab) ? (
        <>
          {activeTab === 'whitelist' && <WhitelistManager />}
          {activeTab === 'requests' && <AccessRequestManager />}
          {activeTab === 'placements' && <PlacementRequestManager />}
          {activeTab === 'users' && <RoleManager />}
          {activeTab === 'database' && <DatabaseBackup />}
          {activeTab === 'config' && <ConfigManager />}
          {activeTab === 'schema' && <EdgeSchemaManager />}
          {activeTab === 'sharing' && <SharingManager />}
        </>
      ) : null}
    </div>
  );
}
