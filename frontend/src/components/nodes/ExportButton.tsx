import { useState, useRef, useEffect } from 'react';
import { Download, ChevronDown } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { exportNodesUrl, exportEdgesUrl, exportCorpusUrl } from '@/api/import-export';

interface ExportButtonProps {
  nodeType?: string;
}

export function ExportButton({ nodeType }: ExportButtonProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleExport = (url: string) => {
    window.open(url, '_blank');
    setOpen(false);
  };

  return (
    <div className="relative" ref={menuRef}>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setOpen(!open)}
        icon={<Download className="h-4 w-4" />}
      >
        Exporteren
        <ChevronDown className="h-3 w-3 ml-1" />
      </Button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-20 w-56 rounded-xl border border-border bg-surface shadow-lg">
          <div className="py-1">
            <button
              onClick={() => handleExport(exportNodesUrl(nodeType))}
              className="flex w-full items-center gap-2 px-4 py-2 text-sm text-text hover:bg-gray-50 transition-colors"
            >
              <Download className="h-4 w-4 text-text-secondary" />
              Nodes als CSV
            </button>
            <button
              onClick={() => handleExport(exportEdgesUrl())}
              className="flex w-full items-center gap-2 px-4 py-2 text-sm text-text hover:bg-gray-50 transition-colors"
            >
              <Download className="h-4 w-4 text-text-secondary" />
              Edges als CSV
            </button>
            <div className="border-t border-border my-1" />
            <button
              onClick={() => handleExport(exportCorpusUrl())}
              className="flex w-full items-center gap-2 px-4 py-2 text-sm text-text hover:bg-gray-50 transition-colors"
            >
              <Download className="h-4 w-4 text-text-secondary" />
              Volledig corpus als JSON
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
