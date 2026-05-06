import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { Upload, X, FileText, Sparkles, Mail, Plus } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import { useCreateLead, useParseLeadIntake, useCheckDuplicates } from '@/hooks/useLeads';
import { addTagToLead as addTagToLeadApi, uploadLeadAttachment as uploadLeadAttachmentApi, addLeadContact as addLeadContactApi } from '@/api/leads';
import { useTags } from '@/hooks/useTags';
import { isEmailFile, parseEmailFile, emailToRawText } from '@/utils/emailParser';
import type { ParsedEmail } from '@/utils/emailParser';
import { useToast } from '@/contexts/ToastContext';
import { usePeople } from '@/hooks/usePeople';
import { useCreateContactPerson } from '@/hooks/useNewContactPerson';
import { NewContactPersonFields } from '@/components/leads/NewContactPersonFields';
import {
  emptyContactPersonFields,
  type ContactPersonFieldsState,
} from '@/components/leads/contactPersonFields';
import { useInitiatieven, useCreateInitiatief } from '@/hooks/useInitiatieven';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { LeadStage, LEAD_STAGE_ORDER, LEAD_STAGE_LABELS, LEAD_STAGE_COLORS, INITIATIEF_COLORS, formatFunctie } from '@/types';
import type { LeadParseResult } from '@/types';
import { buildPersonOptions } from '@/utils/personOptions';

interface LeadIntakeDialogProps {
  open: boolean;
  onClose: () => void;
  defaultInitiatiefId?: string;
  sharedParseResult?: LeadParseResult;
  sharedFiles?: File[];
  initialFiles?: File[];
}

type Step = 'input' | 'parsing' | 'confirm';

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20 MB, matches backend limit

interface ContactEntry {
  personId: string;
  /** Velden voor wanneer er een nieuwe persoon wordt aangemaakt (personId leeg). */
  fields: ContactPersonFieldsState;
  rol: string;
}

const emptyContact = (): ContactEntry => ({
  personId: '',
  fields: emptyContactPersonFields(),
  rol: 'contactpersoon',
});

export function LeadIntakeDialog({ open, onClose, defaultInitiatiefId, sharedParseResult, sharedFiles, initialFiles }: LeadIntakeDialogProps) {
  const [step, setStep] = useState<Step>('input');
  const [rawText, setRawText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [initiatiefId, setInitiatiefId] = useState('');
  const [parseResult, setParseResult] = useState<LeadParseResult | null>(null);
  const [parsedEmail, setParsedEmail] = useState<ParsedEmail | null>(null);
  const [emailParsing, setEmailParsing] = useState(false);
  const emailParsingRef = useRef(false);

  // Editable fields after parse
  const [title, setTitle] = useState('');
  const [organization, setOrganization] = useState('');
  const [description, setDescription] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagSearch, setTagSearch] = useState('');
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const [stage, setStage] = useState<LeadStage>(LeadStage.INBOX);
  const [contacts, setContacts] = useState<ContactEntry[]>([emptyContact()]);
  const updateContact = useCallback((index: number, updates: Partial<ContactEntry>) => {
    setContacts(prev => prev.map((c, i) => i === index ? { ...c, ...updates } : c));
  }, []);
  // Gedeelde lijst zodat een nieuw-toegevoegde expertise zichtbaar is in
  // alle openstaande contact-rijen voordat de server-cache ververst.
  const [extraExpertiseValues, setExtraExpertiseValues] = useState<string[]>([]);
  const addExtraExpertise = useCallback((value: string) => {
    setExtraExpertiseValues((prev) => (prev.includes(value) ? prev : [...prev, value]));
  }, []);
  const [assigneeId, setAssigneeId] = useState<string>('');
  const [broughtById, setBroughtById] = useState<string>('');
  const [leadDate, setLeadDate] = useState(() => new Date().toISOString().split('T')[0]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const createLead = useCreateLead();
  const parseLead = useParseLeadIntake();
  const { showError } = useToast();
  const { currentPerson } = useCurrentPerson();
  const { data: initiatieven } = useInitiatieven();
  const createInitiatiefMutation = useCreateInitiatief();
  const createContact = useCreateContactPerson();
  const { data: people } = usePeople();
  const { data: allTags } = useTags();
  const { openLeadDetail } = useLeadDetail();
  const { data: duplicates } = useCheckDuplicates(title, organization || undefined);
  const tagContainerRef = useRef<HTMLDivElement>(null);

  // Assignee options: current person first (with "(mij)")
  const assigneeOptions = useMemo(
    () => buildPersonOptions(people ?? [], currentPerson, (p) => ({
      value: p.id,
      label: p.naam,
      description: formatFunctie(p.functie),
    })),
    [people, currentPerson],
  );

  // Contact options: plain alphabetical, no "mij" at top
  const contactOptions = useMemo(
    () => (people ?? [])
      .filter((p) => p.is_active)
      .sort((a, b) => a.naam.localeCompare(b.naam))
      .map((p) => ({
        value: p.id,
        label: p.naam,
        description: formatFunctie(p.functie),
      })),
    [people],
  );

  // Auto-select initiative: prefer defaultInitiatiefId, then single-option auto-select
  useEffect(() => {
    if (initiatiefId) return;
    if (defaultInitiatiefId) {
      setInitiatiefId(defaultInitiatiefId);
    } else if (initiatieven?.length === 1) {
      setInitiatiefId(initiatieven[0].id);
    }
  }, [initiatieven, initiatiefId, defaultInitiatiefId]);

  // Default broughtById and leadDate when dialog opens
  useEffect(() => {
    if (open) {
      if (!broughtById && currentPerson) {
        setBroughtById(currentPerson.id);
      }
      if (!leadDate) {
        setLeadDate(new Date().toISOString().split('T')[0]);
      }
    }
  }, [open, broughtById, currentPerson, leadDate]);

  // Apply a parse result to the form fields
  const applyParseResult = useCallback((result: LeadParseResult) => {
    setParseResult(result);
    setTitle(result.title ?? '');
    setOrganization(result.organization ?? '');
    setDescription(result.description ?? '');
    setSelectedTags(result.suggested_tags ?? []);
    setContacts([{
      personId: '',
      fields: {
        ...emptyContactPersonFields(),
        naam: result.contact_name ?? '',
        email: result.contact_email ?? '',
        phone: result.contact_phone ?? '',
      },
      rol: 'contactpersoon',
    }]);
    const today = new Date().toISOString().split('T')[0];
    const parsedDate = result.original_date && /^\d{4}-\d{2}-\d{2}$/.test(result.original_date)
      ? result.original_date
      : today;
    setLeadDate(parsedDate);
    if (result.addressed_to && people) {
      const addr = result.addressed_to.toLowerCase();
      if (currentPerson && currentPerson.naam.toLowerCase().includes(addr)) {
        setBroughtById(currentPerson.id);
      } else {
        const match = people.find(p => p.naam.toLowerCase().startsWith(addr));
        if (match) setBroughtById(match.id);
      }
    }
  }, [people, currentPerson]);

  // Apply shared parse result (from share target) — skip input step
  useEffect(() => {
    if (open && sharedParseResult && step === 'input') {
      applyParseResult(sharedParseResult);
      if (sharedFiles) setFiles(sharedFiles);
      setStep('confirm');
    }
  }, [open, sharedParseResult]); // eslint-disable-line react-hooks/exhaustive-deps

  // Shared helper: validate file sizes and split email vs regular files.
  // Only the first email file is parsed; additional emails are treated as regular files.
  const processEmailAndFiles = useCallback((incoming: File[], replace: boolean) => {
    if (emailParsingRef.current) return; // guard against concurrent email parses

    const emailFile = incoming.find(isEmailFile);
    const rest = incoming.filter(f => f !== emailFile);

    // Size-check all non-email files (email file itself may be large, but we parse it client-side)
    const valid: File[] = [];
    const rejected: string[] = [];
    for (const f of rest) {
      if (f.size > MAX_FILE_SIZE) rejected.push(f.name);
      else valid.push(f);
    }
    if (rejected.length > 0) {
      showError(`Bestanden te groot (max 20 MB): ${rejected.join(', ')}`);
    }

    if (emailFile) {
      emailParsingRef.current = true;
      setEmailParsing(true);
      parseEmailFile(emailFile)
        .then((email) => {
          setParsedEmail(email);
          setRawText(emailToRawText(email));
          // Size-check extracted attachments too
          const validAtts: File[] = [];
          const rejectedAtts: string[] = [];
          for (const att of email.attachments) {
            if (att.size > MAX_FILE_SIZE) rejectedAtts.push(att.name);
            else validAtts.push(att);
          }
          if (rejectedAtts.length > 0) {
            showError(`Bijlagen te groot (max 20 MB): ${rejectedAtts.join(', ')}`);
          }
          const combined = [...validAtts, ...valid];
          if (replace) setFiles(combined);
          else setFiles((prev) => [...prev, ...combined]);
          if (email.senderName || email.senderEmail) {
            setContacts(prev => {
              const updated = [...prev];
              updated[0] = {
                ...updated[0],
                fields: {
                  ...updated[0].fields,
                  naam: email.senderName || updated[0].fields.naam,
                  email: email.senderEmail || updated[0].fields.email,
                },
              };
              return updated;
            });
          }
        })
        .catch(() => {
          showError(`E-mail kon niet worden gelezen: ${emailFile.name}`);
          // Fall back to treating as regular files
          if (replace) setFiles([emailFile, ...valid]);
          else setFiles((prev) => [...prev, emailFile, ...valid]);
        })
        .finally(() => {
          emailParsingRef.current = false;
          setEmailParsing(false);
        });
    } else if (valid.length > 0) {
      if (replace) setFiles(valid);
      else setFiles((prev) => [...prev, ...valid]);
    }
  }, [showError]);

  // Pre-fill files from global drop (stay on input step so user can add text / click parse)
  const prevInitialFilesRef = useRef<File[] | undefined>(undefined);
  useEffect(() => {
    if (!open) {
      prevInitialFilesRef.current = undefined;
      return;
    }
    if (initialFiles && initialFiles.length > 0 && initialFiles !== prevInitialFilesRef.current && !sharedParseResult && step === 'input') {
      prevInitialFilesRef.current = initialFiles;
      processEmailAndFiles(initialFiles, true);
    }
  }, [open, initialFiles]); // eslint-disable-line react-hooks/exhaustive-deps

  // Try to match VLAM's contact_name against existing people
  const firstContactName = contacts[0]?.fields.naam ?? '';
  useEffect(() => {
    if (firstContactName && people) {
      const match = people.find(
        (p) =>
          p.naam.toLowerCase().includes(firstContactName.toLowerCase()) ||
          firstContactName.toLowerCase().includes(p.naam.toLowerCase()),
      );
      if (match) {
        updateContact(0, { personId: match.id });
      }
    }
  }, [firstContactName, people, updateContact]);

  // Filter tags for search dropdown
  const filteredTags = useMemo(
    () =>
      (allTags ?? [])
        .filter((t) => !selectedTags.includes(t.name))
        .filter((t) => (tagSearch ? t.name.toLowerCase().includes(tagSearch.toLowerCase()) : false)),
    [allTags, selectedTags, tagSearch],
  );

  // Close tag dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (tagContainerRef.current && !tagContainerRef.current.contains(e.target as Node)) {
        setTagDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const reset = useCallback(() => {
    setStep('input');
    setRawText('');
    setFiles([]);
    setParseResult(null);
    setParsedEmail(null);
    emailParsingRef.current = false;
    setEmailParsing(false);
    setTitle('');
    setOrganization('');
    setDescription('');
    setSelectedTags([]);
    setTagSearch('');
    setTagDropdownOpen(false);
    setStage(LeadStage.INBOX);
    setContacts([emptyContact()]);
    setExtraExpertiseValues([]);
    setAssigneeId('');
    setBroughtById(currentPerson?.id ?? '');
    setLeadDate(new Date().toISOString().split('T')[0]);
    setInitiatiefId('');
  }, [currentPerson]);

  const handleClose = () => {
    reset();
    onClose();
  };

  const addFiles = useCallback((newFiles: File[]) => {
    processEmailAndFiles(newFiles, false);
  }, [processEmailAndFiles]);

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData.items;
    const pastedFiles: File[] = [];
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        const file = items[i].getAsFile();
        if (file) {
          pastedFiles.push(file);
        }
      }
    }
    if (pastedFiles.length > 0) {
      e.stopPropagation();
      addFiles(pastedFiles);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    addFiles(Array.from(e.dataTransfer.files));
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleParse = async () => {
    if (!rawText.trim() && files.length === 0) return;

    setStep('parsing');
    try {
      const result = await parseLead.mutateAsync({ rawText: rawText.trim() || undefined, files: files.length > 0 ? files : undefined });
      applyParseResult(result);
      setStep('confirm');
    } catch {
      // If parsing fails, go straight to confirm with empty suggestions
      setTitle('');
      setOrganization('');
      setDescription(rawText.slice(0, 200));
      setSelectedTags([]);
      setStep('confirm');
    }
  };

  const handleSkipParse = () => {
    setTitle('');
    setOrganization('');
    setDescription('');
    setSelectedTags([]);
    if (!leadDate) setLeadDate(new Date().toISOString().split('T')[0]);
    setStep('confirm');
  };

  const handleSubmit = async () => {
    if (!title.trim() || !initiatiefId) return;

    const fullDescription = description.trim() || null;

    try {
      const lead = await createLead.mutateAsync({
        title: title.trim(),
        description: fullDescription,
        organization: organization.trim() || null,
        stage,
        raw_intake_text: rawText.trim() || null,
        initiatief_id: initiatiefId,
        assignee_id: assigneeId || null,
        brought_by_id: broughtById || null,
        created_at: leadDate !== new Date().toISOString().split('T')[0]
          ? `${leadDate}T00:00:00Z`
          : null,
      });

      // Add tags via separate endpoint
      for (const tagName of selectedTags) {
        try {
          await addTagToLeadApi(lead.id, { tag_name: tagName });
        } catch {
          // Non-critical, don't block lead creation
        }
      }

      // Upload attached files
      for (const file of files) {
        try {
          await uploadLeadAttachmentApi(lead.id, file);
        } catch {
          // Non-critical, don't block lead creation
        }
      }

      // Add contact persons as LeadContacts
      for (const contact of contacts) {
        if (contact.personId) {
          try {
            await addLeadContactApi(lead.id, contact.personId, contact.rol);
          } catch {
            // Non-critical, don't block lead creation
          }
        } else if (contact.fields.naam.trim()) {
          try {
            let personId: string | null = null;
            // Try to match an existing person by email first to avoid duplicates.
            const email = contact.fields.email.trim();
            if (email && people) {
              const byEmail = people.find(
                (p) => p.email?.toLowerCase() === email.toLowerCase(),
              );
              if (byEmail) personId = byEmail.id;
            }
            if (!personId) {
              const result = await createContact.create({
                naam: contact.fields.naam,
                email: contact.fields.email,
                phone: contact.fields.phone,
                functie: contact.fields.functie,
                expertise: contact.fields.expertise,
                organisatieEenheidId:
                  contact.fields.organisatieEenheidId || undefined,
                samenwerkingsverbandIds: Array.from(
                  contact.fields.samenwerkingsverbandIds,
                ),
              });
              personId = result?.personId ?? null;
              if (!personId) continue;
            }
            await addLeadContactApi(lead.id, personId, contact.rol);
          } catch {
            // Non-critical, don't block lead creation
          }
        }
      }

      handleClose();
    } catch {
      // Error is shown by useMutationWithError
    }
  };

  const canParse = rawText.trim().length > 0 || files.length > 0;
  const canSubmit = title.trim().length > 0 && initiatiefId.length > 0;

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Nieuwe lead"
      size="xl"
    >
      {step === 'input' && (
        <div className="space-y-4">
          {(initiatieven?.length ?? 0) !== 1 && (
            <div>
              <CreatableSelect
                label="Voor welk initiatief is deze lead?"
                value={initiatiefId}
                onChange={setInitiatiefId}
                options={initiatieven?.map((i) => ({
                  value: i.id,
                  label: i.naam,
                })) ?? []}
                placeholder="Selecteer initiatief..."
                onCreate={async (name) => {
                  const kleur = INITIATIEF_COLORS[Math.floor(Math.random() * INITIATIEF_COLORS.length)];
                  const result = await createInitiatiefMutation.mutateAsync({ naam: name, kleur });
                  return result.id;
                }}
                createLabel="Nieuw initiatief"
              />
            </div>
          )}

          {emailParsing && (
            <div className="flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700">
              <LoadingSpinner className="h-4 w-4" />
              E-mail wordt gelezen...
            </div>
          )}

          {parsedEmail && !emailParsing && (
            <div className="flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700">
              <Mail className="h-4 w-4 shrink-0" />
              <span className="truncate">
                E-mail van {parsedEmail.senderName || parsedEmail.senderEmail}
                {parsedEmail.subject ? `: ${parsedEmail.subject}` : ''}
                {parsedEmail.date ? ` (${parsedEmail.date})` : ''}
              </span>
            </div>
          )}

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
              placeholder="Plak tekst, screenshot, of sleep een bestand of e-mail hierheen..."
              className="w-full rounded-xl px-4 py-3 text-sm min-h-[160px] resize-y focus:outline-none bg-transparent"
              rows={6}
              autoFocus
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
                addFiles(Array.from(e.target.files));
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
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                onClick={handleSkipParse}
                disabled={!initiatiefId}
              >
                Handmatig invullen
              </Button>
              <Button
                onClick={handleParse}
                disabled={!canParse || !initiatiefId}
                icon={<Sparkles className="h-4 w-4" />}
              >
                Analyseren met VLAM
              </Button>
            </div>
          </div>
        </div>
      )}

      {step === 'parsing' && (
        <div className="flex flex-col items-center justify-center py-12 gap-3">
          <LoadingSpinner />
          <p className="text-sm text-text-secondary">VLAM analyseert je invoer...</p>
        </div>
      )}

      {step === 'confirm' && (
        <div className="space-y-4">
          {parseResult && (
            <p className="text-xs text-text-secondary bg-gray-50 rounded-lg px-3 py-2">
              VLAM heeft de volgende velden voorgesteld. Pas aan waar nodig.
            </p>
          )}

          {/* Two-column layout */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
            {/* LEFT COLUMN: Lead info */}
            <div className="space-y-4">
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Lead</h4>

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

              {duplicates && duplicates.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                  <p className="text-sm font-medium text-amber-800 mb-1">
                    Vergelijkbare leads gevonden:
                  </p>
                  <ul className="space-y-1">
                    {duplicates.map((d) => (
                      <li key={d.id} className="text-sm">
                        <button
                          type="button"
                          onClick={() => { openLeadDetail(d.id); handleClose(); }}
                          className="text-primary-600 hover:underline"
                        >
                          {d.title}
                        </button>
                        <span className="text-text-secondary ml-1">
                          ({d.organization ?? 'geen organisatie'} - {LEAD_STAGE_LABELS[d.stage as LeadStage]})
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-text mb-1">
                  Status
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {LEAD_STAGE_ORDER.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setStage(s)}
                      className={`rounded-full px-3 py-1 text-xs font-medium transition-all ${
                        stage === s
                          ? `${LEAD_STAGE_COLORS[s]} ring-2 ring-offset-1 ring-current`
                          : 'bg-gray-100 text-text-secondary hover:bg-gray-200'
                      }`}
                    >
                      {LEAD_STAGE_LABELS[s]}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-text mb-1">
                    Datum
                  </label>
                  <input
                    type="date"
                    value={leadDate}
                    onChange={(e) => setLeadDate(e.target.value)}
                    className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
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
              </div>

              <RichTextFormField
                label="Beschrijving"
                value={description}
                onChange={setDescription}
                rows={5}
                placeholder="Korte beschrijving... Gebruik @ voor personen, # voor nodes/taken"
              />

              <div>
                <label className="block text-sm font-medium text-text mb-1">
                  Tags
                </label>

                {/* Selected tags as removable chips */}
                {selectedTags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {selectedTags.map((tag) => (
                      <span
                        key={tag}
                        title={tag}
                        className="inline-flex items-center gap-1 rounded-full bg-slate-100 text-slate-700 px-2.5 py-0.5 text-xs font-medium"
                      >
                        {tag.includes('/') ? tag.split('/').pop() : tag}
                        <button
                          type="button"
                          onClick={() => setSelectedTags((prev) => prev.filter((t) => t !== tag))}
                          className="hover:text-red-500"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}

                {/* Search input for adding tags */}
                <div className="relative" ref={tagContainerRef}>
                  <input
                    type="text"
                    value={tagSearch}
                    onChange={(e) => {
                      setTagSearch(e.target.value);
                      setTagDropdownOpen(true);
                    }}
                    onFocus={() => { if (tagSearch) setTagDropdownOpen(true); }}
                    placeholder="Zoek of typ een tag..."
                    className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && tagSearch.trim()) {
                        e.preventDefault();
                        if (!selectedTags.includes(tagSearch.trim())) {
                          setSelectedTags((prev) => [...prev, tagSearch.trim()]);
                        }
                        setTagSearch('');
                        setTagDropdownOpen(false);
                      }
                    }}
                  />

                  {/* Dropdown with matching existing tags */}
                  {tagDropdownOpen && tagSearch && filteredTags.length > 0 && (
                    <div className="absolute z-10 mt-1 w-full bg-white border border-border rounded-lg shadow-lg max-h-40 overflow-y-auto">
                      {filteredTags.slice(0, 10).map((tag) => (
                        <button
                          key={tag.id}
                          type="button"
                          onClick={() => {
                            setSelectedTags((prev) => [...prev, tag.name]);
                            setTagSearch('');
                            setTagDropdownOpen(false);
                          }}
                          className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition-colors"
                        >
                          {tag.name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* RIGHT COLUMN: People */}
            <div className="space-y-4">
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Personen</h4>

              <CreatableSelect
                label="Binnengebracht door"
                value={broughtById}
                onChange={setBroughtById}
                options={assigneeOptions}
                placeholder="Zoek een teamlid..."
              />

              <CreatableSelect
                label="Verantwoordelijke"
                value={assigneeId}
                onChange={setAssigneeId}
                options={assigneeOptions}
                placeholder="Zoek een persoon..."
                onClear={() => setAssigneeId('')}
              />

              {contacts.map((contact, index) => (
                <div key={index} className="space-y-4">
                  {index > 0 && (
                    <div className="flex items-center justify-between pt-2 border-t border-border">
                      <span className="text-xs font-medium text-text-secondary">Extra externe contactpersoon</span>
                      <button
                        type="button"
                        onClick={() => setContacts(prev => prev.filter((_, i) => i !== index))}
                        className="p-0.5 text-text-secondary hover:text-red-500 transition-colors"
                        title="Verwijderen"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}

                  <CreatableSelect
                    label={index === 0 ? "Externe contactpersoon" : "Extra externe contactpersoon"}
                    value={contact.personId}
                    onChange={(val) => {
                      const person = people?.find((p) => p.id === val);
                      updateContact(index, {
                        personId: val,
                        fields: {
                          ...contact.fields,
                          naam: person?.naam ?? contact.fields.naam,
                        },
                      });
                    }}
                    options={contactOptions}
                    placeholder="Zoek of typ een naam..."
                    onCreate={async (name) => {
                      updateContact(index, {
                        personId: '',
                        fields: { ...contact.fields, naam: name },
                      });
                      return null;
                    }}
                    createLabel="Nieuw contact"
                    displayValue={
                      !contact.personId && contact.fields.naam ? contact.fields.naam : undefined
                    }
                    onClear={() => {
                      updateContact(index, emptyContact());
                    }}
                  />

                  {!contact.personId && contact.fields.naam && (
                    <NewContactPersonFields
                      state={contact.fields}
                      onChange={(next) => updateContact(index, { fields: next })}
                      hideNaam
                      extraExpertiseValues={extraExpertiseValues}
                      onAddExtraExpertise={addExtraExpertise}
                    />
                  )}
                </div>
              ))}

              {contacts.length < 2 && (
                <button
                  type="button"
                  onClick={() => setContacts(prev => [...prev, emptyContact()])}
                  className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-primary-600 transition-colors"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Extra externe contactpersoon toevoegen
                </button>
              )}
            </div>
          </div>

          {/* Files + buttons below both columns */}
          {files.length > 0 && (
            <p className="text-xs text-text-secondary">
              {files.length} {files.length === 1 ? 'bijlage' : 'bijlagen'} worden meegestuurd
            </p>
          )}

          <div className="flex items-center justify-end gap-2 pt-4">
            <Button variant="ghost" onClick={() => setStep('input')}>
              Terug
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!canSubmit}
              loading={createLead.isPending}
            >
              Lead aanmaken
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
