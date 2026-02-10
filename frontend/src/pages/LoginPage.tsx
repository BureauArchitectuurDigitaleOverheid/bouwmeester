import { useAuth } from '@/contexts/AuthContext';

export function LoginPage() {
  const { login } = useAuth();

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-sm w-full space-y-6 text-center">
        <div>
          <h1 className="text-2xl font-semibold text-text">Bouwmeester</h1>
          <p className="mt-2 text-sm text-text-secondary">
            Log in om door te gaan
          </p>
        </div>
        <button
          onClick={login}
          className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 transition-colors"
        >
          Inloggen met SSO Rijk
        </button>
      </div>
    </div>
  );
}
