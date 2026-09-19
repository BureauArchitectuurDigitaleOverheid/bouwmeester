import { useCallback, useRef, useState, useEffect } from 'react';
import { useToast } from '@/contexts/ToastContext';
import { FileUpload } from '@/components/common/FileUpload';
import { NlddButton } from '@/components/nldd/NlddLink';
import { eventValue, orUndef, useNlddEvent, useNlddValue } from '@/components/nldd/events';
import {
  exportDatabase,
  getDatabaseInfo,
  importDatabase,
  resetDatabase,
} from '@/api/import-export';
import type { DatabaseBackupInfo, DatabaseResetResult, DatabaseRestoreResult } from '@/types';

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
  const resetFieldRef = useRef<HTMLElement>(null);

  useNlddEvent(resetFieldRef, 'input', useCallback((e: Event) => setResetConfirmText(eventValue(e)), []));
  useNlddValue(resetFieldRef, resetConfirmText);

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
    <nldd-container max-width="640px" gap="24">
      {/* Export section */}
      <nldd-card>
        <nldd-container gap="16">
          <nldd-container layout="row" gap="12" vertical-alignment="center">
            <nldd-icon name="download" size="24" color="accent" box />
            <nldd-container gap="0">
              <nldd-title size={4}><h2>Database exporteren</h2></nldd-title>
              <nldd-text size="sm" color="secondary">
                Download een volledige backup van de database.
              </nldd-text>
            </nldd-container>
          </nldd-container>

          <nldd-container gap="4">
            <nldd-text size="sm" color="secondary">
              Bevat: corpus, organisatie, personen, taken, audit trail, kamerstukken
            </nldd-text>
            {loadingInfo ? (
              <nldd-text size="sm" color="secondary">Laden...</nldd-text>
            ) : info ? (
              <>
                <nldd-text size="sm" color="secondary">
                  Migratieversie: <code>{info.alembic_revision}</code>
                </nldd-text>
                {info.encrypted && (
                  <nldd-text size="sm" color="secondary">Versleuteling: age-encrypted</nldd-text>
                )}
              </>
            ) : (
              <nldd-text size="sm" color="warning">Kon database-informatie niet ophalen</nldd-text>
            )}
          </nldd-container>

          <nldd-container width="fit-content">
            <NlddButton
              text="Database exporteren"
              startIcon="database"
              onClick={handleExport}
              disabled={exporting}
              loading={exporting}
            />
          </nldd-container>
        </nldd-container>
      </nldd-card>

      {/* Import section */}
      <nldd-card>
        <nldd-container gap="16">
          <nldd-container layout="row" gap="12" vertical-alignment="center">
            <nldd-icon name="upload" size="24" color="warning" box />
            <nldd-container gap="0">
              <nldd-title size={4}><h2>Database importeren</h2></nldd-title>
              <nldd-text size="sm" color="secondary">
                Herstel de database vanuit een backup-bestand.
              </nldd-text>
            </nldd-container>
          </nldd-container>

          <nldd-banner
            variant="warning"
            text="Import vervangt alle huidige data in de database"
            supporting-text="Maak eerst een export als backup. De import kan enkele minuten duren; tijdens het importeren is de applicatie tijdelijk niet beschikbaar voor andere gebruikers."
          />

          <FileUpload
            accept=".tar.gz,.tar.gz.age,.age"
            onFileSelect={handleFileSelect}
            disabled={importing}
            label="Sleep een backup-bestand hierheen of klik om te uploaden"
          />

          {selectedFile && (
            <nldd-container gap="12">
              {confirmImport && (
                <nldd-banner variant="critical" text="Weet je zeker dat je wilt importeren? Alle huidige data wordt vervangen." />
              )}

              <nldd-container layout="row" gap="8">
                <NlddButton
                  text={
                    importing
                      ? 'Bezig met importeren... (dit kan enkele minuten duren)'
                      : confirmImport
                        ? 'Bevestig import'
                        : 'Database importeren'
                  }
                  startIcon="upload"
                  variant={confirmImport ? 'destructive' : 'primary'}
                  onClick={handleImport}
                  disabled={importing}
                  loading={importing}
                />
                {confirmImport && (
                  <NlddButton text="Annuleren" variant="neutral-tinted" onClick={() => setConfirmImport(false)} />
                )}
              </nldd-container>
            </nldd-container>
          )}

          {restoreResult && (
            <nldd-banner
              variant={restoreResult.success ? 'success' : 'critical'}
              text={restoreResult.message}
              supporting-text={
                `${restoreResult.tables_restored} tabellen hersteld` +
                (restoreResult.migrations_applied > 0
                  ? ` · ${restoreResult.migrations_applied} migraties toegepast`
                  : '') +
                ` · versie ${restoreResult.alembic_revision_to}`
              }
            />
          )}
        </nldd-container>
      </nldd-card>

      {/* Reset section */}
      <nldd-box background="critical">
        <nldd-container gap="16">
          <nldd-container layout="row" gap="12" vertical-alignment="center">
            <nldd-icon name="delete" size="24" color="critical" box />
            <nldd-container gap="0">
              <nldd-title size={4}><h2>Database resetten</h2></nldd-title>
              <nldd-text size="sm" color="secondary">Wis alle data en begin opnieuw.</nldd-text>
            </nldd-container>
          </nldd-container>

          <nldd-banner
            variant="critical"
            text="Dit wist alle data behalve de toegangslijst en sessies"
            supporting-text="Corpus, organisatie, personen, taken — alles wordt verwijderd. Admin-accounts worden opnieuw aangemaakt. De applicatie is tijdelijk niet beschikbaar tijdens het resetten."
          />

          {!showResetInput ? (
            <nldd-container width="fit-content">
              <NlddButton
                text="Database resetten"
                startIcon="delete"
                variant="destructive"
                onClick={() => setShowResetInput(true)}
              />
            </nldd-container>
          ) : (
            <nldd-container gap="12">
              <nldd-form-field label="Type RESET om te bevestigen">
                <nldd-text-field
                  ref={resetFieldRef}
                  placeholder="RESET"
                  disabled={orUndef(resetting)}
                  width="240px"
                />
              </nldd-form-field>

              <nldd-container layout="row" gap="8">
                <NlddButton
                  text={resetting ? 'Bezig met resetten...' : 'Bevestig reset'}
                  startIcon="delete"
                  variant="destructive"
                  onClick={handleReset}
                  disabled={resetting || resetConfirmText !== 'RESET'}
                  loading={resetting}
                />
                <NlddButton
                  text="Annuleren"
                  variant="neutral-tinted"
                  disabled={resetting}
                  onClick={() => {
                    setShowResetInput(false);
                    setResetConfirmText('');
                  }}
                />
              </nldd-container>
            </nldd-container>
          )}

          {resetResult && (
            <nldd-banner
              variant={resetResult.success ? 'success' : 'critical'}
              text={resetResult.message}
              supporting-text={
                `${resetResult.tables_cleared} tabellen gewist` +
                (resetResult.admin_persons_created > 0
                  ? ` · ${resetResult.admin_persons_created} admin-accounts aangemaakt`
                  : '')
              }
            />
          )}
        </nldd-container>
      </nldd-box>
    </nldd-container>
  );
}
