import { useState, useEffect } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { WhitelistManager } from '@/components/admin/WhitelistManager';
import { UserManager } from '@/components/admin/UserManager';
import { DatabaseBackup } from '@/components/admin/DatabaseBackup';
import { AccessRequestManager } from '@/components/admin/AccessRequestManager';
import { ConfigManager } from '@/components/admin/ConfigManager';

type Tab = 'whitelist' | 'users' | 'database' | 'requests' | 'config';

export function AdminPage() {
  const { person, oidcConfigured, loading } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as Tab | null;
  const [activeTab, setActiveTab] = useState<Tab>(tabParam || 'whitelist');

  // Sync tab from URL param
  useEffect(() => {
    if (tabParam && ['whitelist', 'users', 'database', 'requests', 'config'].includes(tabParam)) {
      setActiveTab(tabParam);
    }
  }, [tabParam]);

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    setSearchParams(tab === 'whitelist' ? {} : { tab });
  };

  // While loading auth, show nothing (prevents flash of admin UI)
  if (loading) {
    return null;
  }

  // In OIDC mode: redirect non-admins immediately (before rendering content)
  if (oidcConfigured && (!person || !person.is_admin)) {
    return <Navigate to="/" replace />;
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: 'whitelist', label: 'Toegangslijst' },
    { id: 'requests', label: 'Verzoeken' },
    { id: 'users', label: 'Gebruikers' },
    { id: 'database', label: 'Database' },
    { id: 'config', label: 'Instellingen' },
  ];

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
      {activeTab === 'whitelist' && <WhitelistManager />}
      {activeTab === 'requests' && <AccessRequestManager />}
      {activeTab === 'users' && <UserManager />}
      {activeTab === 'database' && <DatabaseBackup />}
      {activeTab === 'config' && <ConfigManager />}
    </div>
  );
}
