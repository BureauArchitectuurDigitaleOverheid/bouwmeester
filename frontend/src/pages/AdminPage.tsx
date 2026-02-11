import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { WhitelistManager } from '@/components/admin/WhitelistManager';
import { UserManager } from '@/components/admin/UserManager';

type Tab = 'whitelist' | 'users';

export function AdminPage() {
  const { person, oidcConfigured, loading } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>('whitelist');

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
    { id: 'users', label: 'Gebruikers' },
  ];

  return (
    <div className="p-4 md:p-6 max-w-4xl">
      {/* Tab bar */}
      <div className="flex gap-1 border-b border-border mb-6">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
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
      {activeTab === 'users' && <UserManager />}
    </div>
  );
}
