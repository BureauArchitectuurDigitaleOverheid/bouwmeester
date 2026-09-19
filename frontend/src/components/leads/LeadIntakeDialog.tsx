import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { NlddButton } from '@/components/nldd/NlddLink';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { eventValue, useNlddEvent } from '@/components/nldd/events';
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
import { INITIATIEF_COLORS, formatFunctie } from '@/types';
import { useLeadColumns } from '@/hooks/useLeadColumns';
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
  const [stage, setStage] = useState<string>('inbox');
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
  const { columns: stageColumns } = useLeadColumns(initiatiefId || undefined);
  const sortedStageColumns = useMemo(
    () => [...stageColumns].sort((a, b) => a.sort_order - b.sort_order),
    [stageColumns],
  );
  const stageColumnsBySlug = useMemo(() => {
    const map = new Map<string, (typeof sortedStageColumns)[number]>();
    for (const c of sortedStageColumns) map.set(c.slug, c);
    return map;
  }, [sortedStageColumns]);
  // Wanneer het initiatief verandert kan de geselecteerde stage niet langer
  // bestaan in de kolommen van dat initiatief. Val terug op de eerste kolom.
  useEffect(() => {
    if (sortedStageColumns.length === 0) return;
    if (!stageColumnsBySlug.has(stage)) {
      setStage(sortedStageColumns[0].slug);
    }
  }, [sortedStageColumns, stageColumnsBySlug, stage]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const rawTextFieldRef = useRef<HTMLElement>(null);
  useNlddEvent(rawTextFieldRef, 'input', useCallback((e: Event) => setRawText(eventValue(e)), []));
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
    setStage('inbox');
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
            <div className="flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2">
              <LoadingSpinner className="h-4 w-4" />
              <nldd-text size="sm" color="accent">E-mail wordt gelezen...</nldd-text>
            </div>
          )}

          {parsedEmail && !emailParsing && (
            <div className="flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2">
              <nldd-icon name="envelope" size="16" color="accent" aria-hidden="true" />
              <nldd-text size="sm" color="accent" className="truncate">
                E-mail van {parsedEmail.senderName || parsedEmail.senderEmail}
                {parsedEmail.subject ? `: ${parsedEmail.subject}` : ''}
                {parsedEmail.date ? ` (${parsedEmail.date})` : ''}
              </nldd-text>
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
            <nldd-multi-line-text-field
              ref={rawTextFieldRef}
              value={rawText}
              placeholder="Plak tekst, screenshot, of sleep een bestand of e-mail hierheen..."
              accessible-label="Ruwe invoer voor lead-analyse"
              rows={6}
              autoFocus
              width="full"
            />
            {dragActive && (
              <div className="absolute inset-0 flex items-center justify-center bg-primary-50/80 rounded-xl pointer-events-none">
                <div className="flex items-center gap-2 text-primary-600 font-medium text-sm">
                  <nldd-icon name="upload" size="20" aria-hidden="true" />
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
                  className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-1.5"
                >
                  {file.type.startsWith('image/') ? (
                    <img
                      src={URL.createObjectURL(file)}
                      alt={file.name}
                      className="h-8 w-8 rounded object-cover"
                    />
                  ) : (
                    <nldd-icon name="file-text" size="16" aria-hidden="true" />
                  )}
                  <nldd-text size="sm" color="secondary" className="flex-1 truncate">{file.name}</nldd-text>
                  <NlddIconButton
                    icon="close"
                    accessibleLabel="Bestand verwijderen"
                    variant="neutral-transparent"
                    size="sm"
                    onClick={() => removeFile(i)}
                  />
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
              icon="upload"
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
                icon="sparkles"
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
            <nldd-text size="xs" color="secondary" className="block bg-gray-50 rounded-lg px-3 py-2">
              VLAM heeft de volgende velden voorgesteld. Pas aan waar nodig.
            </nldd-text>
          )}

          {/* Two-column layout */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
            {/* LEFT COLUMN: Lead info */}
            <div className="space-y-4">
              <nldd-text size="xs" weight="medium" color="secondary" className="uppercase tracking-wide">Lead</nldd-text>

              <Input
                label="Titel"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Titel van de lead"
                required
                autoFocus
              />

              {duplicates && duplicates.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                  <nldd-text size="sm" weight="medium" color="warning" className="block mb-1">
                    Vergelijkbare leads gevonden:
                  </nldd-text>
                  <div className="space-y-1">
                    {duplicates.map((d) => (
                      <DuplicateLeadLink
                        key={d.id}
                        title={d.title}
                        detail={`${d.organization ?? 'geen organisatie'} - ${stageColumnsBySlug.get(d.stage)?.name ?? d.stage}`}
                        onOpen={() => { openLeadDetail(d.id); handleClose(); }}
                      />
                    ))}
                  </div>
                </div>
              )}

              <nldd-form-field label="Status">
                <div className="flex flex-wrap gap-1.5">
                  {sortedStageColumns.map((c) => (
                    <StagePill
                      key={c.id}
                      name={c.name}
                      colorClass={c.color}
                      active={stage === c.slug}
                      onSelect={() => setStage(c.slug)}
                    />
                  ))}
                </div>
              </nldd-form-field>

              <div className="grid grid-cols-2 gap-3">
                <Input
                  label="Datum"
                  type="date"
                  value={leadDate}
                  onChange={(e) => setLeadDate(e.target.value)}
                />
                <Input
                  label="Organisatie"
                  type="text"
                  value={organization}
                  onChange={(e) => setOrganization(e.target.value)}
                  placeholder="Naam van de organisatie"
                  autoComplete="organization"
                />
              </div>

              <RichTextFormField
                label="Beschrijving"
                value={description}
                onChange={setDescription}
                rows={5}
                placeholder="Korte beschrijving... Gebruik @ voor personen, # voor nodes/taken"
              />

              <nldd-form-field label="Tags">
                {/* Selected tags as removable chips */}
                {selectedTags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {selectedTags.map((tag) => (
                      <RemovableTagChip
                        key={tag}
                        tag={tag}
                        onRemove={() => setSelectedTags((prev) => prev.filter((t) => t !== tag))}
                      />
                    ))}
                  </div>
                )}

                {/* Search input for adding tags */}
                <div className="relative" ref={tagContainerRef}>
                  <TagSearchField
                    value={tagSearch}
                    onChange={(v) => {
                      setTagSearch(v);
                      setTagDropdownOpen(true);
                    }}
                    onFocus={() => { if (tagSearch) setTagDropdownOpen(true); }}
                    onSubmit={() => {
                      if (tagSearch.trim() && !selectedTags.includes(tagSearch.trim())) {
                        setSelectedTags((prev) => [...prev, tagSearch.trim()]);
                      }
                      setTagSearch('');
                      setTagDropdownOpen(false);
                    }}
                  />

                  {/* Dropdown with matching existing tags */}
                  {tagDropdownOpen && tagSearch && filteredTags.length > 0 && (
                    <nldd-list variant="box-tinted" dividers="never" className="absolute z-10 mt-1 w-full max-h-40 overflow-y-auto" accessible-label="Tag-suggesties">
                      {filteredTags.slice(0, 10).map((tag) => (
                        <TagSuggestionItem
                          key={tag.id}
                          name={tag.name}
                          onSelect={() => {
                            setSelectedTags((prev) => [...prev, tag.name]);
                            setTagSearch('');
                            setTagDropdownOpen(false);
                          }}
                        />
                      ))}
                    </nldd-list>
                  )}
                </div>
              </nldd-form-field>
            </div>

            {/* RIGHT COLUMN: People */}
            <div className="space-y-4">
              <nldd-text size="xs" weight="medium" color="secondary" className="uppercase tracking-wide">Personen</nldd-text>

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
                      <nldd-text size="xs" weight="medium" color="secondary">Extra externe contactpersoon</nldd-text>
                      <NlddIconButton
                        icon="close"
                        accessibleLabel="Verwijderen"
                        variant="neutral-transparent"
                        size="sm"
                        onClick={() => setContacts(prev => prev.filter((_, i) => i !== index))}
                      />
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
                <NlddButton
                  variant="neutral-transparent"
                  size="sm"
                  text="Extra externe contactpersoon toevoegen"
                  startIcon="plus"
                  onClick={() => setContacts(prev => [...prev, emptyContact()])}
                />
              )}
            </div>
          </div>

          {/* Files + buttons below both columns */}
          {files.length > 0 && (
            <nldd-text size="xs" color="secondary">
              {files.length} {files.length === 1 ? 'bijlage' : 'bijlagen'} worden meegestuurd
            </nldd-text>
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

interface StagePillProps {
  name: string;
  colorClass: string;
  active: boolean;
  onSelect: () => void;
}

/**
 * A stage's color (`colorClass`) is a raw Tailwind chip class tied to
 * per-initiatief lead-column data (same shape as LEAD_STAGE_COLORS), not one
 * of the five semantic roles — kept as a styled span rather than nldd-tag.
 */
function StagePill({ name, colorClass, active, onSelect }: StagePillProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onSelect);

  return (
    <nldd-list-item-segment
      ref={ref}
      button
      className={`rounded-full px-3 py-1 text-xs font-medium transition-all ${
        active ? `${colorClass} ring-2 ring-offset-1 ring-current` : 'bg-gray-100 text-text-secondary hover:bg-gray-200'
      }`}
    >
      {name}
    </nldd-list-item-segment>
  );
}

interface DuplicateLeadLinkProps {
  title: string;
  detail: string;
  onOpen: () => void;
}

function DuplicateLeadLink({ title, detail, onOpen }: DuplicateLeadLinkProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onOpen);

  return (
    <div className="text-sm">
      <NlddButton variant="neutral-transparent" size="xs" text={title} onClick={onOpen} className="p-0 h-auto" />
      <nldd-text size="sm" color="secondary" className="ml-1">({detail})</nldd-text>
    </div>
  );
}

interface RemovableTagChipProps {
  tag: string;
  onRemove: () => void;
}

/**
 * nldd-tag has no dismiss affordance (it is a static label, per its own
 * template — no click semantics, no end-icon slot), so a removable chip stays
 * a plain styled span with a real icon button rather than forcing the tag
 * component into a role it does not support.
 */
function RemovableTagChip({ tag, onRemove }: RemovableTagChipProps) {
  const display = tag.includes('/') ? tag.split('/').pop() : tag;
  return (
    <span
      title={tag}
      className="inline-flex items-center gap-1 rounded-full bg-slate-100 text-slate-700 px-2.5 py-0.5 text-xs font-medium"
    >
      {display}
      <NlddIconButton
        icon="close"
        accessibleLabel={`${tag} verwijderen`}
        variant="neutral-transparent"
        size="xs"
        onClick={onRemove}
      />
    </span>
  );
}

interface TagSearchFieldProps {
  value: string;
  onChange: (value: string) => void;
  onFocus: () => void;
  onSubmit: () => void;
}

function TagSearchField({ value, onChange, onFocus, onSubmit }: TagSearchFieldProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', useCallback((e: Event) => onChange(eventValue(e)), [onChange]));
  useNlddEvent(ref, 'focus', onFocus);
  useNlddEvent(
    ref,
    'keydown',
    useCallback(
      (e: Event) => {
        if ((e as KeyboardEvent).key === 'Enter') {
          e.preventDefault();
          onSubmit();
        }
      },
      [onSubmit],
    ),
  );

  return (
    <nldd-text-field
      ref={ref}
      value={value}
      placeholder="Zoek of typ een tag..."
      accessible-label="Zoek of typ een tag"
      width="full"
    />
  );
}

interface TagSuggestionItemProps {
  name: string;
  onSelect: () => void;
}

function TagSuggestionItem({ name, onSelect }: TagSuggestionItemProps) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onSelect);

  return (
    <nldd-list-item ref={ref} button accessible-label={name}>
      <nldd-text-cell text={name} />
    </nldd-list-item>
  );
}
