import { useState, useEffect } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { WhitelistManager } from '@/components/admin/WhitelistManager';
import { UserManager } from '@/components/admin/UserManager';
import { DatabaseBackup } from '@/components/admin/DatabaseBackup';
import { AccessRequestManager } from '@/components/admin/AccessRequestManager';

type Tab = 'whitelist' | 'users' | 'database' | 'requests';

export function AdminPage() {
  const { person, oidcConfigured, loading } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as Tab | null;
  const [activeTab, setActiveTab] = useState<Tab>(tabParam || 'whitelist');

  // Sync tab from URL param
  useEffect(() => {
    if (tabParam && ['whitelist', 'users', 'database', 'requests'].includes(tabParam)) {
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
  ];

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      {/* Tab bar */}
      <div className="flex gap-1 border-b border-border mb-6">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
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
    </div>
  );
}
