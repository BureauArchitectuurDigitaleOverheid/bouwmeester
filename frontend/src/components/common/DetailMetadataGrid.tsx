import type { ReactNode } from 'react';

interface MetadataItem {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  span?: 1 | 2;
}

interface DetailMetadataGridProps {
  items: MetadataItem[];
  separated?: boolean;
}

export function DetailMetadataGrid({ items, separated = false }: DetailMetadataGridProps) {
  const visibleItems = items.filter((item) => item.value != null && item.value !== '');

  if (visibleItems.length === 0) return null;

  return (
    <div className={`grid grid-cols-2 gap-4 text-sm ${separated ? 'border-t border-border pt-4' : ''}`}>
      {visibleItems.map((item) => (
        <div key={item.label} className={item.span === 2 ? 'col-span-2' : ''}>
          <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
            {item.label}
          </h4>
          <span className="inline-flex items-center gap-1.5 text-text-secondary">
            {item.icon}
            {item.value}
          </span>
        </div>
      ))}
    </div>
  );
}
