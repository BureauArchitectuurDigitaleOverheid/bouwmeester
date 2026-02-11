import { useAdminUsers, useToggleAdmin } from '@/hooks/useAdmin';
import { useAuth } from '@/contexts/AuthContext';
import { formatFunctie } from '@/types';

export function UserManager() {
  const { data: users, isLoading } = useAdminUsers();
  const toggleAdmin = useToggleAdmin();
  const { person: authPerson } = useAuth();

  if (isLoading) {
    return <div className="text-sm text-text-secondary py-8 text-center">Laden...</div>;
  }

  return (
    <div className="space-y-4">
      <div className="border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-border">
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary">Naam</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden sm:table-cell">E-mail</th>
              <th className="text-left px-4 py-2.5 font-medium text-text-secondary hidden md:table-cell">Functie</th>
              <th className="text-center px-4 py-2.5 font-medium text-text-secondary w-24">Admin</th>
            </tr>
          </thead>
          <tbody>
            {users?.map((user) => {
              const isSelf = authPerson?.id === user.id;
              return (
                <tr key={user.id} className="border-b border-border last:border-b-0 hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-2.5 text-text">
                    {user.naam}
                    {isSelf && (
                      <span className="ml-1.5 text-xs text-text-secondary">(jij)</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-text-secondary hidden sm:table-cell">
                    {user.email || '-'}
                  </td>
                  <td className="px-4 py-2.5 text-text-secondary hidden md:table-cell">
                    {formatFunctie(user.functie) || '-'}
                  </td>
                  <td className="px-4 py-2.5 text-center">
                    <button
                      onClick={() =>
                        toggleAdmin.mutate({ id: user.id, is_admin: !user.is_admin })
                      }
                      disabled={toggleAdmin.isPending || isSelf}
                      title={isSelf ? 'Je kunt je eigen admin-rechten niet wijzigen' : undefined}
                      className={`inline-flex items-center justify-center w-10 h-6 rounded-full transition-colors ${
                        user.is_admin
                          ? 'bg-primary-600'
                          : 'bg-gray-200'
                      } ${isSelf ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                    >
                      <span
                        className={`block w-4 h-4 rounded-full bg-white shadow transition-transform ${
                          user.is_admin ? 'translate-x-2' : '-translate-x-2'
                        }`}
                      />
                    </button>
                  </td>
                </tr>
              );
            })}
            {(!users || users.length === 0) && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-text-secondary">
                  Geen gebruikers gevonden
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-text-secondary">
        Admins hebben toegang tot dit beheerpaneel en kunnen de toegangslijst en admin-rollen beheren.
      </p>
    </div>
  );
}
