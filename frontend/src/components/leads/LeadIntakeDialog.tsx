import { useState, useRef, useCallback } from 'react';
import { Upload, X, FileText, Sparkles } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useCreateLead, useUploadLeadAttachment, useParseLeadIntake } from '@/hooks/useLeads';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { LeadStage } from '@/types';
import type { LeadParseResult } from '@/types';

interface LeadIntakeDialogProps {
  open: boolean;
  onClose: () => void;
}

type Step = 'input' | 'parsing' | 'confirm';

export function LeadIntakeDialog({ open, onClose }: LeadIntakeDialogProps) {
  const [step, setStep] = useState<Step>('input');
  const [rawText, setRawText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [orgEenheidId, setOrgEenheidId] = useState('');
  const [parseResult, setParseResult] = useState<LeadParseResult | null>(null);

  // Editable fields after parse
  const [title, setTitle] = useState('');
  const [organization, setOrganization] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const createLead = useCreateLead();
  const uploadAttachment = useUploadLeadAttachment();
  const parseLead = useParseLeadIntake();
  const { data: orgEenheden } = useOrganisatieFlat();
  const { currentPerson } = useCurrentPerson();

  const reset = useCallback(() => {
    setStep('input');
    setRawText('');
    setFiles([]);
    setParseResult(null);
    setTitle('');
    setOrganization('');
    setDescription('');
    setTags('');
    setOrgEenheidId('');
  }, []);

  const handleClose = () => {
    reset();
    onClose();
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData.items;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        const file = items[i].getAsFile();
        if (file) {
          setFiles((prev) => [...prev, file]);
        }
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const droppedFiles = Array.from(e.dataTransfer.files);
    setFiles((prev) => [...prev, ...droppedFiles]);
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleParse = async () => {
    if (!rawText.trim() && files.length === 0) return;

    setStep('parsing');
    try {
      const result = await parseLead.mutateAsync({ rawText: rawText.trim() || undefined, files: files.length > 0 ? files : undefined });
      setParseResult(result);
      setTitle(result.title ?? '');
      setOrganization(result.organization ?? '');
      setDescription(result.description ?? '');
      setTags(result.suggested_tags?.join(', ') ?? '');
      setStep('confirm');
    } catch {
      // If parsing fails, go straight to confirm with empty suggestions
      setTitle('');
      setOrganization('');
      setDescription(rawText.slice(0, 200));
      setTags('');
      setStep('confirm');
    }
  };

  const handleSkipParse = () => {
    setTitle('');
    setOrganization('');
    setDescription('');
    setTags('');
    setStep('confirm');
  };

  const handleSubmit = async () => {
    if (!title.trim() || !orgEenheidId) return;

    const tagList = tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      const lead = await createLead.mutateAsync({
        title: title.trim(),
        description: description.trim() || null,
        organization: organization.trim() || null,
        stage: LeadStage.VERKENNEN,
        tags: tagList,
        raw_intake_text: rawText.trim() || null,
        organisatie_eenheid_id: orgEenheidId,
      });

      // Upload attached files
      for (const file of files) {
        await uploadAttachment.mutateAsync({ leadId: lead.id, file });
      }

      handleClose();
    } catch {
      // Error is shown by useMutationWithError
    }
  };

  const canParse = rawText.trim().length > 0 || files.length > 0;
  const canSubmit = title.trim().length > 0 && orgEenheidId.length > 0;

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Nieuwe lead"
      size="lg"
    >
      {step === 'input' && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text mb-1">
              Organisatie-eenheid
            </label>
            <select
              value={orgEenheidId}
              onChange={(e) => setOrgEenheidId(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
            >
              <option value="">Selecteer eenheid...</option>
              {orgEenheden?.map((org) => (
                <option key={org.id} value={org.id}>
                  {org.naam}
                </option>
              ))}
            </select>
          </div>

          <div
            onPaste={handlePaste}
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            className={`relative rounded-xl border-2 border-dashed transition-colors ${
              dragActive
                ? 'border-primary-400 bg-primary-50/50'
                : 'border-border'
            }`}
          >
            <textarea
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              placeholder="Plak tekst, screenshot, of sleep een bestand hierheen..."
              className="w-full rounded-xl px-4 py-3 text-sm min-h-[160px] resize-y focus:outline-none bg-transparent"
              rows={6}
            />
            {dragActive && (
              <div className="absolute inset-0 flex items-center justify-center bg-primary-50/80 rounded-xl pointer-events-none">
                <div className="flex items-center gap-2 text-primary-600 font-medium text-sm">
                  <Upload className="h-5 w-5" />
                  Sleep bestanden hierheen
                </div>
              </div>
            )}
          </div>

          {files.length > 0 && (
            <div className="space-y-1">
              {files.map((file, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-1.5 text-sm"
                >
                  {file.type.startsWith('image/') ? (
                    <img
                      src={URL.createObjectURL(file)}
                      alt={file.name}
                      className="h-8 w-8 rounded object-cover"
                    />
                  ) : (
                    <FileText className="h-4 w-4 text-text-secondary" />
                  )}
                  <span className="flex-1 truncate text-text-secondary">{file.name}</span>
                  <button
                    onClick={() => removeFile(i)}
                    className="p-0.5 text-text-secondary hover:text-red-500 transition-colors"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files) {
                setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
              }
            }}
          />

          <div className="flex items-center justify-between gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              icon={<Upload className="h-4 w-4" />}
            >
              Bestand toevoegen
            </Button>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSkipParse}
                disabled={!orgEenheidId}
              >
                Handmatig invullen
              </Button>
              <Button
                size="sm"
                onClick={handleParse}
                disabled={!canParse || !orgEenheidId}
                icon={<Sparkles className="h-4 w-4" />}
              >
                Analyseren
              </Button>
            </div>
          </div>
        </div>
      )}

      {step === 'parsing' && (
        <div className="flex flex-col items-center justify-center py-12 gap-3">
          <LoadingSpinner />
          <p className="text-sm text-text-secondary">Tekst wordt geanalyseerd...</p>
        </div>
      )}

      {step === 'confirm' && (
        <div className="space-y-4">
          {parseResult && (
            <p className="text-xs text-text-secondary bg-gray-50 rounded-lg px-3 py-2">
              Voorgestelde velden op basis van analyse. Pas aan waar nodig.
            </p>
          )}

          <div>
            <label className="block text-sm font-medium text-text mb-1">
              Titel <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
              placeholder="Titel van de lead"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text mb-1">
              Organisatie
            </label>
            <input
              type="text"
              value={organization}
              onChange={(e) => setOrganization(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
              placeholder="Naam van de organisatie"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text mb-1">
              Beschrijving
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400 min-h-[80px] resize-y"
              placeholder="Korte beschrijving"
              rows={3}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text mb-1">
              Tags
            </label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
              placeholder="Komma-gescheiden tags"
            />
          </div>

          {files.length > 0 && (
            <p className="text-xs text-text-secondary">
              {files.length} {files.length === 1 ? 'bijlage' : 'bijlagen'} worden meegestuurd
            </p>
          )}

          <div className="flex items-center justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={() => setStep('input')}>
              Terug
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!canSubmit}
              loading={createLead.isPending || uploadAttachment.isPending}
            >
              Lead aanmaken
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
