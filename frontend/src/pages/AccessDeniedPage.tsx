import { BASE_URL } from '@/api/client';

interface AccessDeniedPageProps {
  email: string | null;
}

export function AccessDeniedPage({ email }: AccessDeniedPageProps) {
  const handleLogout = () => {
    window.location.href = `${BASE_URL}/api/auth/logout`;
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-6 text-center">
        <div>
          <h1 className="text-2xl font-semibold text-text">Bouwmeester</h1>
          <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-6">
            <h2 className="text-lg font-medium text-amber-800">Geen toegang</h2>
            {email && (
              <p className="mt-2 text-sm text-amber-700">
                Ingelogd als <span className="font-medium">{email}</span>
              </p>
            )}
            <p className="mt-3 text-sm text-amber-700">
              Je account staat niet op de toegangslijst voor deze applicatie.
              Neem contact op met een beheerder om toegang aan te vragen.
            </p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="w-full flex justify-center py-2.5 px-4 border border-border rounded-lg shadow-sm text-sm font-medium text-text hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors"
        >
          Uitloggen en opnieuw proberen
        </button>
      </div>
    </div>
  );
}
