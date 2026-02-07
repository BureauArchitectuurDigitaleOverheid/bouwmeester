import { useState } from 'react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { FileUpload } from '@/components/common/FileUpload';
import { importNodes, importEdges, importPolitiekeInputs, type ImportResult } from '@/api/import-export';
import { Upload, CheckCircle, AlertTriangle } from 'lucide-react';

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
              icon={<Upload className="h-4 w-4" />}
            >
              Importeren
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        {/* Import type selector */}
        <div>
          <label className="block text-sm font-medium text-text mb-1.5">
            Type import
          </label>
          <select
            value={importType}
            onChange={(e) => {
              setImportType(e.target.value as ImportType);
              setResult(null);
              setError(null);
            }}
            className="w-full rounded-xl border border-border px-3 py-2 text-sm text-text bg-white focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
          >
            {(Object.entries(IMPORT_TYPE_LABELS) as [ImportType, string][]).map(
              ([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ),
            )}
          </select>
        </div>

        {/* CSV format hint */}
        <div className="rounded-lg bg-blue-50 border border-blue-200 px-4 py-3">
          <p className="text-sm font-medium text-blue-800 mb-1">Verwacht CSV-formaat</p>
          <p className="text-xs text-blue-700 font-mono">
            {importType === 'nodes' && 'title, node_type, description, status'}
            {importType === 'edges' && 'from_node_title, to_node_title, edge_type_id, description'}
            {importType === 'politieke-inputs' &&
              'title, type, referentie, datum, description, status'}
          </p>
        </div>

        {/* File upload */}
        <FileUpload
          accept=".csv"
          onFileSelect={setSelectedFile}
          disabled={loading}
        />

        {/* Error message */}
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-600 shrink-0" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        )}

        {/* Result summary */}
        {result && (
          <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 space-y-2">
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-green-600 shrink-0" />
              <p className="text-sm font-medium text-green-800">Import voltooid</p>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-green-700">Geimporteerd:</span>{' '}
                <span className="font-medium text-green-800">{result.imported}</span>
              </div>
              <div>
                <span className="text-amber-700">Overgeslagen:</span>{' '}
                <span className="font-medium text-amber-800">{result.skipped}</span>
              </div>
            </div>
            {result.errors.length > 0 && (
              <div className="mt-2">
                <p className="text-xs font-medium text-red-700 mb-1">Fouten:</p>
                <ul className="max-h-32 overflow-y-auto space-y-0.5">
                  {result.errors.map((err, i) => (
                    <li key={i} className="text-xs text-red-600">
                      {err}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
