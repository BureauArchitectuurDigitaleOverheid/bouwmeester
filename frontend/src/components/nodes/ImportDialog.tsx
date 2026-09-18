import { useState } from 'react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { FileUpload } from '@/components/common/FileUpload';
import { Select } from '@/components/common/Select';
import { importNodes, importEdges, importPolitiekeInputs } from '@/api/import-export';
import type { ImportResult } from '@/types';

type ImportType = 'nodes' | 'edges' | 'politieke-inputs';

interface ImportDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

const IMPORT_TYPE_LABELS: Record<ImportType, string> = {
  nodes: 'Nodes',
  edges: 'Edges',
  'politieke-inputs': 'Politieke Inputs',
};

export function ImportDialog({ open, onClose, onSuccess }: ImportDialogProps) {
  const [importType, setImportType] = useState<ImportType>('nodes');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleImport = async () => {
    if (!selectedFile) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      let importResult: ImportResult;

      switch (importType) {
        case 'nodes':
          importResult = await importNodes(selectedFile);
          break;
        case 'edges':
          importResult = await importEdges(selectedFile);
          break;
        case 'politieke-inputs':
          importResult = await importPolitiekeInputs(selectedFile);
          break;
      }

      setResult(importResult);
      if (importResult.imported > 0) {
        onSuccess?.();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import mislukt');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setSelectedFile(null);
    setResult(null);
    setError(null);
    setLoading(false);
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Importeren"
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={handleClose}>
            {result ? 'Sluiten' : 'Annuleren'}
          </Button>
          {!result && (
            <Button
              onClick={handleImport}
              loading={loading}
              disabled={!selectedFile}
              icon="upload"
            >
              Importeren
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        {/* Import type selector */}
        <Select
          label="Type import"
          value={importType}
          onChange={(e) => {
            setImportType(e.target.value as ImportType);
            setResult(null);
            setError(null);
          }}
          options={(Object.entries(IMPORT_TYPE_LABELS) as [ImportType, string][]).map(
            ([value, label]) => ({ value, label }),
          )}
        />

        {/* CSV format hint */}
        <nldd-banner
          variant="accent"
          size="sm"
          text="Verwacht CSV-formaat"
          supporting-text={
            importType === 'nodes'
              ? 'title, node_type, description, status'
              : importType === 'edges'
                ? 'from_node_title, to_node_title, edge_type_id, description'
                : 'title, type, referentie, datum, description, status'
          }
        />

        {/* File upload */}
        <FileUpload
          accept=".csv"
          onFileSelect={setSelectedFile}
          disabled={loading}
        />

        {/* Error message */}
        {error && <nldd-banner variant="critical" size="sm" text={error} />}

        {/* Result summary */}
        {result && (
          <nldd-banner variant="success" size="sm" text="Import voltooid">
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span>Geimporteerd:</span>{' '}
                <span className="font-medium">{result.imported}</span>
              </div>
              <div>
                <span>Overgeslagen:</span>{' '}
                <span className="font-medium">{result.skipped}</span>
              </div>
            </div>
            {result.errors.length > 0 && (
              <div className="max-h-32 overflow-y-auto">
                <nldd-list dividers="never">
                  {result.errors.map((err, i) => (
                    <nldd-list-item key={i}>
                      <nldd-text-cell size="sm" color="critical" text={err} />
                    </nldd-list-item>
                  ))}
                </nldd-list>
              </div>
            )}
          </nldd-banner>
        )}
      </div>
    </Modal>
  );
}
