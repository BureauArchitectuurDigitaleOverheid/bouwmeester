import { useState, useEffect } from 'react';
import { Download, Upload, AlertTriangle, CheckCircle, Loader2, Database, Trash2 } from 'lucide-react';
import { useToast } from '@/contexts/ToastContext';
import { FileUpload } from '@/components/common/FileUpload';
import {
  exportDatabase,
  getDatabaseInfo,
  importDatabase,
  resetDatabase,
  type DatabaseBackupInfo,
  type DatabaseResetResult,
  type DatabaseRestoreResult,
} from '@/api/import-export';

export function DatabaseBackup() {
  const { showError, showSuccess } = useToast();
  const [info, setInfo] = useState<DatabaseBackupInfo | null>(null);
  const [loadingInfo, setLoadingInfo] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [restoreResult, setRestoreResult] = useState<DatabaseRestoreResult | null>(null);
  const [confirmImport, setConfirmImport] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetConfirmText, setResetConfirmText] = useState('');
  const [showResetInput, setShowResetInput] = useState(false);
  const [resetResult, setResetResult] = useState<DatabaseResetResult | null>(null);

  useEffect(() => {
    getDatabaseInfo()
      .then(setInfo)
      .catch(() => setInfo(null))
      .finally(() => setLoadingInfo(false));
  }, []);

  const handleExport = async () => {
    setExporting(true);
    try {
      await exportDatabase();
      showSuccess('Export voltooid — het bestand wordt gedownload.');
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Export mislukt';
      showError(msg);
    } finally {
      setExporting(false);
    }
  };

  const handleFileSelect = (file: File) => {
    setSelectedFile(file);
    setRestoreResult(null);
    setConfirmImport(false);
  };

  const handleImport = async () => {
    if (!selectedFile) return;

    if (!confirmImport) {
      setConfirmImport(true);
      return;
    }

    setImporting(true);
    setRestoreResult(null);
    try {
      const result = await importDatabase(selectedFile);
      setRestoreResult(result);
      if (result.success) {
        showSuccess(result.message);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Import mislukt';
      showError(msg);
    } finally {
      setImporting(false);
      setConfirmImport(false);
    }
  };

  const handleReset = async () => {
    setResetting(true);
    setResetResult(null);
    try {
      const result = await resetDatabase(resetConfirmText);
      setResetResult(result);
      if (result.success) {
        showSuccess(result.message);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Reset mislukt';
      showError(msg);
    } finally {
      setResetting(false);
      setResetConfirmText('');
      setShowResetInput(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      {/* Export section */}
      <section className="rounded-xl border border-border bg-surface p-5 space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-primary-50">
            <Download className="h-5 w-5 text-primary-600" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-text">Database exporteren</h2>
            <p className="text-sm text-text-secondary">
              Download een volledige backup van de database.
            </p>
          </div>
        </div>

        <div className="text-sm text-text-secondary space-y-1">
          <p>Bevat: corpus, organisatie, personen, taken, audit trail, kamerstukken</p>
          {loadingInfo ? (
            <p className="flex items-center gap-1.5">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Laden...
            </p>
          ) : info ? (
            <>
              <p>Migratieversie: <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{info.alembic_revision}</code></p>
              {info.encrypted && <p>Versleuteling: age-encrypted</p>}
            </>
          ) : (
            <p className="text-amber-600">Kon database-informatie niet ophalen</p>
          )}
        </div>

        <button
          onClick={handleExport}
          disabled={exporting}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
        >
          {exporting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Database className="h-4 w-4" />
          )}
          Database exporteren
        </button>
      </section>

      {/* Import section */}
      <section className="rounded-xl border border-border bg-surface p-5 space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-amber-50">
            <Upload className="h-5 w-5 text-amber-600" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-text">Database importeren</h2>
            <p className="text-sm text-text-secondary">
              Herstel de database vanuit een backup-bestand.
            </p>
          </div>
        </div>

        <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 p-3">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <div className="text-sm text-amber-800 space-y-1">
            <p>
              Import vervangt <strong>alle</strong> huidige data in de database.
              Maak eerst een export als backup.
            </p>
            <p>
              De import kan enkele minuten duren. Tijdens het importeren is de
              applicatie tijdelijk niet beschikbaar voor andere gebruikers.
            </p>
          </div>
        </div>

        <FileUpload
          accept=".tar.gz,.tar.gz.age,.age"
          onFileSelect={handleFileSelect}
          disabled={importing}
          label="Sleep een backup-bestand hierheen of klik om te uploaden"
        />

        {selectedFile && (
          <div className="space-y-3">
            {confirmImport && (
              <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3">
                <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />
                <p className="text-sm text-red-800">
                  Weet je zeker dat je wilt importeren? Alle huidige data wordt vervangen.
                </p>
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={handleImport}
                disabled={importing}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-white text-sm font-medium disabled:opacity-50 transition-colors ${
                  confirmImport
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-amber-600 hover:bg-amber-700'
                }`}
              >
                {importing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
                {importing ? 'Bezig met importeren... (dit kan enkele minuten duren)' : confirmImport ? 'Bevestig import' : 'Database importeren'}
              </button>

              {confirmImport && (
                <button
                  onClick={() => setConfirmImport(false)}
                  className="px-4 py-2 rounded-lg border border-border text-sm text-text-secondary hover:bg-gray-50 transition-colors"
                >
                  Annuleren
                </button>
              )}
            </div>
          </div>
        )}

        {restoreResult && (
          <div className={`flex items-start gap-2 rounded-lg p-3 ${
            restoreResult.success
              ? 'bg-green-50 border border-green-200'
              : 'bg-red-50 border border-red-200'
          }`}>
            <CheckCircle className={`h-4 w-4 mt-0.5 shrink-0 ${
              restoreResult.success ? 'text-green-600' : 'text-red-600'
            }`} />
            <div className="text-sm space-y-1">
              <p className={restoreResult.success ? 'text-green-800' : 'text-red-800'}>
                {restoreResult.message}
              </p>
              <p className="text-text-secondary">
                {restoreResult.tables_restored} tabellen hersteld
                {restoreResult.migrations_applied > 0 && (
                  <> &middot; {restoreResult.migrations_applied} migraties toegepast</>
                )}
                {' '}&middot; versie {restoreResult.alembic_revision_to}
              </p>
            </div>
          </div>
        )}
      </section>

      {/* Reset section */}
      <section className="rounded-xl border border-red-200 bg-surface p-5 space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-red-50">
            <Trash2 className="h-5 w-5 text-red-600" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-text">Database resetten</h2>
            <p className="text-sm text-text-secondary">
              Wis alle data en begin opnieuw.
            </p>
          </div>
        </div>

        <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3">
          <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />
          <div className="text-sm text-red-800 space-y-1">
            <p>
              Dit wist <strong>alle</strong> data behalve de toegangslijst en sessies.
              Corpus, organisatie, personen, taken — alles wordt verwijderd.
              Admin-accounts worden opnieuw aangemaakt.
            </p>
            <p>
              De applicatie is tijdelijk niet beschikbaar tijdens het resetten.
            </p>
          </div>
        </div>

        {!showResetInput ? (
          <button
            onClick={() => setShowResetInput(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-red-300 text-red-600 text-sm font-medium hover:bg-red-50 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
            Database resetten
          </button>
        ) : (
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-text mb-1">
                Type <code className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">RESET</code> om te bevestigen
              </label>
              <input
                type="text"
                value={resetConfirmText}
                onChange={(e) => setResetConfirmText(e.target.value)}
                placeholder="RESET"
                className="w-48 px-3 py-2 rounded-lg border border-border text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-red-500"
                disabled={resetting}
                autoFocus
              />
            </div>

            <div className="flex gap-2">
              <button
                onClick={handleReset}
                disabled={resetting || resetConfirmText !== 'RESET'}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {resetting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                {resetting ? 'Bezig met resetten...' : 'Bevestig reset'}
              </button>

              <button
                onClick={() => {
                  setShowResetInput(false);
                  setResetConfirmText('');
                }}
                disabled={resetting}
                className="px-4 py-2 rounded-lg border border-border text-sm text-text-secondary hover:bg-gray-50 transition-colors"
              >
                Annuleren
              </button>
            </div>
          </div>
        )}

        {resetResult && (
          <div className={`flex items-start gap-2 rounded-lg p-3 ${
            resetResult.success
              ? 'bg-green-50 border border-green-200'
              : 'bg-red-50 border border-red-200'
          }`}>
            <CheckCircle className={`h-4 w-4 mt-0.5 shrink-0 ${
              resetResult.success ? 'text-green-600' : 'text-red-600'
            }`} />
            <div className="text-sm space-y-1">
              <p className={resetResult.success ? 'text-green-800' : 'text-red-800'}>
                {resetResult.message}
              </p>
              <p className="text-text-secondary">
                {resetResult.tables_cleared} tabellen gewist
                {resetResult.admin_persons_created > 0 && (
                  <> &middot; {resetResult.admin_persons_created} admin-accounts aangemaakt</>
                )}
              </p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
