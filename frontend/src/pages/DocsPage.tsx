import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';

interface DocTab {
  id: string;
  label: string;
}

export function DocsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tabs, setTabs] = useState<DocTab[]>([]);
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [tabsLoading, setTabsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const tabParam = searchParams.get('tab');

  // Load the manifest once
  useEffect(() => {
    fetch('/docs/index.json')
      .then((res) => {
        if (!res.ok) throw new Error(`Kon documentatie-index niet laden (${res.status})`);
        return res.json();
      })
      .then((data: DocTab[]) => {
        setTabs(data);
        setTabsLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setTabsLoading(false);
      });
  }, []);

  // Determine active tab from URL or default to first
  const activeTab = tabs.find((t) => t.id === tabParam)?.id ?? tabs[0]?.id;

  // Load content when active tab changes
  useEffect(() => {
    if (!activeTab) return;
    setLoading(true);
    setError(null);
    fetch(`/docs/${activeTab}.md`)
      .then((res) => {
        if (!res.ok) throw new Error(`Kon documentatie niet laden (${res.status})`);
        return res.text();
      })
      .then((text) => {
        setContent(text);
        setLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  }, [activeTab]);

  const handleTabChange = (tabId: string) => {
    setSearchParams({ tab: tabId });
  };

  if (tabsLoading) {
    return (
      <div className="max-w-4xl mx-auto px-4 md:px-6 py-6">
        <div className="flex items-center justify-center py-12">
          <div className="text-sm text-text-secondary">Laden...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 md:px-6 py-6">
      {/* Tabs */}
      {tabs.length > 1 && (
        <div className="flex gap-1 mb-6 border-b border-border overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-primary-600 text-primary-700'
                  : 'border-transparent text-text-secondary hover:text-text hover:border-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="text-sm text-text-secondary">Laden...</div>
        </div>
      )}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
          {error}
        </div>
      )}
      {!loading && !error && <MarkdownRenderer content={content} />}
    </div>
  );
}
