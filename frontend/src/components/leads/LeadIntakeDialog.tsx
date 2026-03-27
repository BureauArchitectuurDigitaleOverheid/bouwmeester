import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { Upload, X, FileText, Sparkles } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { useCreateLead, useUploadLeadAttachment, useParseLeadIntake, useAddLeadContact, useAddTagToLead, useCheckDuplicates } from '@/hooks/useLeads';
import { useTags } from '@/hooks/useTags';
import { usePeople, usePersonOrganisaties } from '@/hooks/usePeople';
import { createPerson } from '@/api/people';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useLeadDetail } from '@/contexts/LeadDetailContext';
import { LeadStage, LEAD_STAGE_ORDER, LEAD_STAGE_LABELS, LEAD_STAGE_COLORS, formatFunctie } from '@/types';
import type { LeadParseResult } from '@/types';
import { buildPersonOptions } from '@/utils/personOptions';

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
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagSearch, setTagSearch] = useState('');
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const [stage, setStage] = useState<LeadStage>(LeadStage.VERKENNEN);
  const [contactName, setContactName] = useState('');
  const [contactPersonId, setContactPersonId] = useState<string>('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [assigneeId, setAssigneeId] = useState<string>('');
  const [broughtById, setBroughtById] = useState<string>('');
  const [leadDate, setLeadDate] = useState(() => new Date().toISOString().split('T')[0]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const createLead = useCreateLead();
  const uploadAttachment = useUploadLeadAttachment();
  const parseLead = useParseLeadIntake();
  const addLeadContact = useAddLeadContact();
  const addTagToLead = useAddTagToLead();
  const { currentPerson } = useCurrentPerson();
  const { data: personPlaatsingen } = usePersonOrganisaties(currentPerson?.id ?? null);
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

  const myEenheden = personPlaatsingen ?? [];

  // Auto-select if user has exactly one eenheid
  useEffect(() => {
    if (myEenheden.length === 1 && !orgEenheidId) {
      setOrgEenheidId(myEenheden[0].organisatie_eenheid_id);
    }
  }, [myEenheden, orgEenheidId]);

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

  // Try to match VLAM's contact_name against existing people
  useEffect(() => {
    if (contactName && people) {
      const match = people.find(
        (p) =>
          p.naam.toLowerCase().includes(contactName.toLowerCase()) ||
          contactName.toLowerCase().includes(p.naam.toLowerCase()),
      );
      if (match) {
        setContactPersonId(match.id);
      }
    }
  }, [contactName, people]);

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
    setTitle('');
    setOrganization('');
    setDescription('');
    setSelectedTags([]);
    setTagSearch('');
    setTagDropdownOpen(false);
    setStage(LeadStage.VERKENNEN);
    setContactName('');
    setContactPersonId('');
    setContactEmail('');
    setContactPhone('');
    setAssigneeId('');
    setBroughtById(currentPerson?.id ?? '');
    setLeadDate(new Date().toISOString().split('T')[0]);
    setOrgEenheidId('');
  }, [currentPerson]);

  const handleClose = () => {
    reset();
    onClose();
  };

  const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20 MB, matches backend limit

  const addFiles = useCallback((newFiles: File[]) => {
    const valid: File[] = [];
    const rejected: string[] = [];
    for (const f of newFiles) {
      if (f.size > MAX_FILE_SIZE) {
        rejected.push(f.name);
      } else {
        valid.push(f);
      }
    }
    if (rejected.length > 0) {
      window.alert(`Bestanden te groot (max 20 MB): ${rejected.join(', ')}`);
    }
    if (valid.length > 0) {
      setFiles((prev) => [...prev, ...valid]);
    }
  }, []);

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
      addFiles(pastedFiles);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
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
      setParseResult(result);
      setTitle(result.title ?? '');
      setOrganization(result.organization ?? '');
      setDescription(result.description ?? '');
      setSelectedTags(result.suggested_tags ?? []);
      setContactName(result.contact_name ?? '');
      setContactEmail(result.contact_email ?? '');
      setContactPhone(result.contact_phone ?? '');
      const today = new Date().toISOString().split('T')[0];
      const parsedDate = result.original_date && /^\d{4}-\d{2}-\d{2}$/.test(result.original_date)
        ? result.original_date
        : today;
      setLeadDate(parsedDate);
      if (result.addressed_to && people) {
        const addr = result.addressed_to.toLowerCase();
        // Prioritize the current person (if "Anne" matches "Anne Schuth" who is logged in)
        if (currentPerson && currentPerson.naam.toLowerCase().includes(addr)) {
          setBroughtById(currentPerson.id);
        } else {
          // Fall back to first match in people list
          const match = people.find(p =>
            p.naam.toLowerCase().startsWith(addr),
          );
          if (match) setBroughtById(match.id);
        }
      }
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
    if (!title.trim() || !orgEenheidId) return;

    const fullDescription = description.trim() || null;

    try {
      const lead = await createLead.mutateAsync({
        title: title.trim(),
        description: fullDescription,
        organization: organization.trim() || null,
        stage,
        raw_intake_text: rawText.trim() || null,
        organisatie_eenheid_id: orgEenheidId,
        assignee_id: assigneeId || null,
        brought_by_id: broughtById || null,
        created_at: leadDate !== new Date().toISOString().split('T')[0]
          ? `${leadDate}T00:00:00Z`
          : null,
      });

      // Add tags via separate endpoint
      for (const tagName of selectedTags) {
        try {
          await addTagToLead.mutateAsync({ leadId: lead.id, data: { tag_name: tagName } });
        } catch {
          // Non-critical, don't block lead creation
        }
      }

      // Upload attached files
      for (const file of files) {
        try {
          await uploadAttachment.mutateAsync({ leadId: lead.id, file });
        } catch {
          // Non-critical, don't block lead creation
        }
      }

      // Add contact person as LeadContact
      if (contactPersonId) {
        // Existing person matched - link as contact
        try {
          await addLeadContact.mutateAsync({
            leadId: lead.id,
            personId: contactPersonId,
            rol: 'contactpersoon',
          });
        } catch {
          // Non-critical, don't block lead creation
        }
      } else if (contactName.trim()) {
        // New person - try to find by email first, otherwise create
        try {
          let personId: string | null = null;
          if (contactEmail.trim() && people) {
            const byEmail = people.find(
              (p) => p.email?.toLowerCase() === contactEmail.trim().toLowerCase(),
            );
            if (byEmail) personId = byEmail.id;
          }
          if (!personId) {
            const newPerson = await createPerson({
              naam: contactName.trim(),
              email: contactEmail.trim() || undefined,
            });
            personId = newPerson.id;
          }
          await addLeadContact.mutateAsync({
            leadId: lead.id,
            personId,
            rol: 'contactpersoon',
          });
        } catch {
          // Non-critical, don't block lead creation
        }
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
      size="xl"
    >
      {step === 'input' && (
        <div className="space-y-4">
          {myEenheden.length !== 1 && (
            <div>
              <label className="block text-sm font-medium text-text mb-1">
                Voor welk team is deze lead?
              </label>
              <select
                value={orgEenheidId}
                onChange={(e) => setOrgEenheidId(e.target.value)}
                className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
              >
                <option value="">Selecteer team...</option>
                {myEenheden.map((p) => (
                  <option key={p.organisatie_eenheid_id} value={p.organisatie_eenheid_id}>
                    {p.organisatie_eenheid_naam}
                  </option>
                ))}
              </select>
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
              placeholder="Plak tekst, screenshot, of sleep een bestand hierheen..."
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
                disabled={!orgEenheidId}
              >
                Handmatig invullen
              </Button>
              <Button
                onClick={handleParse}
                disabled={!canParse || !orgEenheidId}
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

              <CreatableSelect
                label="Contactpersoon (extern)"
                value={contactPersonId}
                onChange={(val) => {
                  setContactPersonId(val);
                  const person = people?.find((p) => p.id === val);
                  if (person) setContactName(person.naam);
                }}
                options={contactOptions}
                placeholder="Zoek of typ een naam..."
                onCreate={async (name) => {
                  setContactName(name);
                  setContactPersonId('');
                  return null;
                }}
                createLabel="Nieuw contact"
                displayValue={!contactPersonId && contactName ? contactName : undefined}
                onClear={() => {
                  setContactPersonId('');
                  setContactName('');
                  setContactEmail('');
                  setContactPhone('');
                }}
              />

              {(contactPersonId || contactName) && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-text mb-1">
                      E-mail
                    </label>
                    <input
                      type="email"
                      value={contactEmail}
                      onChange={(e) => setContactEmail(e.target.value)}
                      className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
                      placeholder="email@organisatie.nl"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-text mb-1">
                      Telefoon
                    </label>
                    <input
                      type="tel"
                      value={contactPhone}
                      onChange={(e) => setContactPhone(e.target.value)}
                      className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
                      placeholder="06-12345678"
                    />
                  </div>
                </div>
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
