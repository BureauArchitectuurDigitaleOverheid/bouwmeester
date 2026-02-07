import { useLocation } from 'react-router-dom';
import { Search, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const pageTitles: Record<string, string> = {
  '/': 'Inbox',
  '/corpus': 'Corpus',
  '/tasks': 'Taken',
  '/people': 'Personen',
  '/organisatie': 'Organisatie',
  '/search': 'Zoeken',
};

export function Header() {
  const location = useLocation();
  const navigate = useNavigate();

  const pathBase = '/' + (location.pathname.split('/')[1] || '');
  const title = pageTitles[pathBase] || 'Bouwmeester';

  const isDetailPage = location.pathname.match(/^\/nodes\/.+/);
  const breadcrumbs = isDetailPage
    ? [
        { label: 'Corpus', href: '/corpus' },
        { label: 'Detail', href: undefined },
      ]
    : undefined;

  return (
    <header className="flex items-center justify-between h-16 px-6 bg-surface border-b border-border shrink-0">
      {/* Left: Title / Breadcrumbs */}
      <div className="flex items-center gap-2">
        {breadcrumbs ? (
          <nav className="flex items-center gap-1.5 text-sm">
            {breadcrumbs.map((crumb, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-text-secondary">/</span>}
                {crumb.href ? (
                  <button
                    onClick={() => navigate(crumb.href!)}
                    className="text-text-secondary hover:text-text transition-colors"
                  >
                    {crumb.label}
                  </button>
                ) : (
                  <span className="text-text font-medium">{crumb.label}</span>
                )}
              </span>
            ))}
          </nav>
        ) : (
          <h1 className="text-lg font-semibold text-text">{title}</h1>
        )}
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-3">
        {/* Search shortcut */}
        <button
          onClick={() => navigate('/search')}
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-border text-sm text-text-secondary hover:border-border-hover hover:text-text transition-all"
        >
          <Search className="h-4 w-4" />
          <span className="hidden sm:inline">Zoeken...</span>
          <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-gray-100 text-[10px] font-medium text-text-secondary">
            /
          </kbd>
        </button>

        {/* User avatar placeholder */}
        <div className="flex items-center justify-center h-8 w-8 rounded-full bg-primary-100 text-primary-700">
          <User className="h-4 w-4" />
        </div>
      </div>
    </header>
  );
}
