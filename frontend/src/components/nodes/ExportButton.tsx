import { useId } from 'react';
import { Button } from '@/components/common/Button';
import { exportNodesUrl, exportEdgesUrl, exportCorpusUrl, exportArchimateUrl } from '@/api/import-export';

interface ExportButtonProps {
  nodeType?: string;
  hideLabel?: boolean;
}

export function ExportButton({ nodeType, hideLabel }: ExportButtonProps) {
  const triggerId = useId();

  return (
    <>
      <Button id={triggerId} variant="secondary" icon="download">
        {/* `Button` reads this exact className to detect a responsively-hidden
            label and turn it into the button's accessible name on narrow
            screens (see findResponsivelyHiddenLabel in common/Button.tsx) —
            it is the wrapper's own API contract, not decorative Tailwind. */}
        <span className={hideLabel ? 'hidden sm:inline' : undefined}>Exporteren</span>
      </Button>

      <nldd-menu anchor={triggerId} accessible-label="Exportopties">
        <nldd-menu-item text="Nodes als CSV" icon="download" href={exportNodesUrl(nodeType)} />
        <nldd-menu-item text="Edges als CSV" icon="download" href={exportEdgesUrl()} />
        <nldd-menu-divider />
        <nldd-menu-item text="Volledig corpus als JSON" icon="download" href={exportCorpusUrl()} />
        <nldd-menu-item text="ArchiMate XML" icon="download" href={exportArchimateUrl()} />
      </nldd-menu>
    </>
  );
}
