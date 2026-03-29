import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Camera, Loader2, Lock, Share2 } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { LeadIntakeDialog } from '@/components/leads/LeadIntakeDialog';
import { useParseLeadIntake } from '@/hooks/useLeads';
import { usePermissions } from '@/hooks/usePermissions';
import type { LeadParseResult } from '@/types';

interface SharedData {
  title: string;
  text: string;
  files: File[];
  previews: string[];
}

async function readSharedData(): Promise<SharedData | null> {
  try {
    const cache = await caches.open('share-target-cache');

    const metaResp = await cache.match('/_share-meta');
    if (!metaResp) return null;
    const meta = await metaResp.json();

    const files: File[] = [];
    const previews: string[] = [];

    for (let i = 0; i < meta.fileCount; i++) {
      const fileResp = await cache.match(`/_share-file-${i}`);
      if (!fileResp) continue;
      const blob = await fileResp.blob();
      const filename = fileResp.headers.get('X-Filename') || `shared-${i}.jpg`;
      const contentType = fileResp.headers.get('Content-Type') || 'image/jpeg';
      files.push(new File([blob], filename, { type: contentType }));
      previews.push(URL.createObjectURL(blob));
    }

    // Clean up cache
    await cache.delete('/_share-meta');
    for (let i = 0; i < meta.fileCount; i++) {
      await cache.delete(`/_share-file-${i}`);
    }

    return {
      title: meta.title || '',
      text: meta.text || '',
      files,
      previews,
    };
  } catch {
    return null;
  }
}

export function ShareTargetPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const received = searchParams.get('received') === '1';

  const [sharedData, setSharedData] = useState<SharedData | null>(null);
  const [parseResult, setParseResult] = useState<LeadParseResult | null>(null);
  const [showDialog, setShowDialog] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parseMutation = useParseLeadIntake();
  const { hasPermission } = usePermissions();
  const canCreateLeads = hasPermission('lead:read');

  // Read shared data from cache on mount
  useEffect(() => {
    if (!received || !canCreateLeads) return;
    readSharedData().then((data) => {
      if (data && data.files.length > 0) {
        setSharedData(data);
      } else {
        setError('Geen afbeeldingen ontvangen.');
      }
    });
  }, [received]);

  // Auto-parse when shared data arrives
  useEffect(() => {
    if (!sharedData || parsing || parseResult) return;

    setParsing(true);
    const rawText = [sharedData.title, sharedData.text].filter(Boolean).join('\n') || undefined;

    parseMutation.mutateAsync({ rawText, files: sharedData.files })
      .then((result) => {
        setParseResult(result);
        setShowDialog(true);
        setParsing(false);
      })
      .catch(() => {
        setError('Kon de afbeelding niet analyseren. Probeer het opnieuw.');
        setParsing(false);
      });
  }, [sharedData]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDialogClose = () => {
    setShowDialog(false);
    // Clean up blob URLs
    sharedData?.previews.forEach(URL.revokeObjectURL);
    navigate('/leads');
  };

  // No lead permission — show access denied
  if (received && !canCreateLeads) {
    return (
      <div className="max-w-md mx-auto py-20 text-center space-y-6">
        <div className="w-16 h-16 rounded-2xl bg-amber-50 flex items-center justify-center mx-auto">
          <Lock className="h-8 w-8 text-amber-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-text mb-2">Geen toegang</h2>
          <p className="text-sm text-text-secondary">
            Je hebt geen rechten om leads aan te maken. Neem contact op met een beheerder.
          </p>
        </div>
        <Button variant="secondary" onClick={() => navigate('/')}>
          Naar startpagina
        </Button>
      </div>
    );
  }

  // Not a share — show instructions
  if (!received) {
    return (
      <div className="max-w-md mx-auto py-20 text-center space-y-6">
        <div className="w-16 h-16 rounded-2xl bg-primary-50 flex items-center justify-center mx-auto">
          <Share2 className="h-8 w-8 text-primary-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-text mb-2">Deel naar Bouwmeester</h2>
          <p className="text-sm text-text-secondary leading-relaxed">
            Deel een afbeelding vanuit je telefoon (foto's, WhatsApp, e-mail)
            via het deelmenu en kies Bouwmeester. De afbeelding wordt
            automatisch geanalyseerd en omgezet naar een nieuwe lead.
          </p>
          <p className="text-xs text-text-secondary mt-4">
            Vereist dat de app is geinstalleerd via "Toevoegen aan startscherm".
          </p>
        </div>
        <Button variant="secondary" onClick={() => navigate('/leads')}>
          Naar leads
        </Button>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="max-w-md mx-auto py-20 text-center space-y-6">
        <div className="w-16 h-16 rounded-2xl bg-red-50 flex items-center justify-center mx-auto">
          <Camera className="h-8 w-8 text-red-500" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-text mb-2">Oeps</h2>
          <p className="text-sm text-text-secondary">{error}</p>
        </div>
        <Button variant="secondary" onClick={() => navigate('/leads')}>
          Naar leads
        </Button>
      </div>
    );
  }

  // Parsing state — show preview + spinner
  return (
    <>
      <div className="max-w-md mx-auto py-12 text-center space-y-8">
        {/* Image previews */}
        {sharedData && sharedData.previews.length > 0 && (
          <div className="flex justify-center gap-3">
            {sharedData.previews.map((src, i) => (
              <div
                key={i}
                className="w-32 h-32 rounded-2xl overflow-hidden border border-border shadow-sm"
              >
                <img
                  src={src}
                  alt={`Gedeelde afbeelding ${i + 1}`}
                  className="w-full h-full object-cover"
                />
              </div>
            ))}
          </div>
        )}

        {/* Status */}
        {parsing && (
          <div className="space-y-3">
            <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto" />
            <p className="text-sm font-medium text-text">Afbeelding analyseren...</p>
            <p className="text-xs text-text-secondary">
              Contactgegevens en organisatie worden herkend
            </p>
          </div>
        )}

        {!parsing && !sharedData && !error && (
          <div className="space-y-3">
            <Loader2 className="h-6 w-6 text-text-secondary animate-spin mx-auto" />
            <p className="text-sm text-text-secondary">Gedeelde data ophalen...</p>
          </div>
        )}
      </div>

      {/* Lead creation dialog with parsed data */}
      <LeadIntakeDialog
        open={showDialog}
        onClose={handleDialogClose}
        sharedParseResult={parseResult ?? undefined}
        sharedFiles={sharedData?.files}
      />
    </>
  );
}
