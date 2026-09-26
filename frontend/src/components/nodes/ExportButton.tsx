import { useId } from 'react';
import { exportNodesUrl, exportEdgesUrl, exportCorpusUrl, exportArchimateUrl } from '@/api/import-export';
import { NlddButton } from '@/components/nldd/NlddButton';

interface ExportButtonProps {
  nodeType?: string;
  hideLabel?: boolean;
}

export function ExportButton({ nodeType, hideLabel }: ExportButtonProps) {
  const triggerId = useId();

  return (
    <>
      <NlddButton
        id={triggerId}
        variant="secondary"
        startIcon="download"
        text="Exporteren"
        compactBelowSm={hideLabel}
      />

      <nldd-menu anchor={triggerId}>
        <nldd-menu-item text="Nodes als CSV" icon="download" href={exportNodesUrl(nodeType)} />
        <nldd-menu-item text="Edges als CSV" icon="download" href={exportEdgesUrl()} />
        <nldd-menu-divider />
        <nldd-menu-item text="Volledig corpus als JSON" icon="download" href={exportCorpusUrl()} />
        <nldd-menu-item text="ArchiMate XML" icon="download" href={exportArchimateUrl()} />
      </nldd-menu>
    </>
  );
}
