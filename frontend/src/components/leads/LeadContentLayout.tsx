import { useState, useMemo, useRef, useEffect, useCallback, type ReactNode } from 'react';
import { User, Calendar, X } from 'lucide-react';
import { InlineEditableField } from '@/components/common/InlineEditableField';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { Badge } from '@/components/common/Badge';
import { usePeople } from '@/hooks/usePeople';
import { useInitiatieven, useCreateInitiatief } from '@/hooks/useInitiatieven';
import { useTags } from '@/hooks/useTags';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { buildPersonOptions } from '@/utils/personOptions';
import { createPerson } from '@/api/people';
import { isOverdue, formatDateLong } from '@/utils/dates';
import {
  LeadStage,
  LEAD_STAGE_LABELS,
  LEAD_STAGE_COLORS,
  LEAD_STAGE_ORDER,
  INITIATIEF_COLORS,
  formatFunctie,
} from '@/types';

export interface LeadContentLayoutProps {
  // Lead data
  title: string;
  stage: LeadStage;
  description: string | null;
  organization: string | null;
  assigneeId: string | null;
  assigneeName: string | null;
  broughtById: string | null;
  broughtByName: string | null;
  initiatiefId: string | null;
  initiatiefName: string | null;
  initiatiefKleur: string | null;
  nextAction: string | null;
  nextActionDate: string | null;
  createdAt: string | null;
  tags: string[];

  // Per-field save callbacks (omit to make read-only)
  onTitleChange?: (value: string) => Promise<void>;
  onStageChange?: (value: LeadStage) => Promise<void>;
  onDescriptionChange?: (value: string | null) => Promise<void>;
  onOrganizationChange?: (value: string | null) => Promise<void>;
  onAssigneeChange?: (value: string | null) => Promise<void>;
  onBroughtByChange?: (value: string | null) => Promise<void>;
  onInitiatiefChange?: (value: string | null) => Promise<void>;
  onNextActionChange?: (value: string | null) => Promise<void>;
  onNextActionDateChange?: (value: string | null) => Promise<void>;
  onTagsChange?: (tags: string[]) => Promise<void>;
  onCreatedAtChange?: (value: string | null) => Promise<void>;

  // Context-specific sections
  rightColumnChildren?: ReactNode;
  bottomChildren?: ReactNode;
}

function StagePills({
  value,
  onChange,
}: {
  value: LeadStage;
  onChange?: (stage: LeadStage) => Promise<void>;
}) {
  const [saving, setSaving] = useState(false);

  if (!onChange) {
    return (
      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${LEAD_STAGE_COLORS[value]}`}>
        {LEAD_STAGE_LABELS[value]}
      </span>
    );
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {LEAD_STAGE_ORDER.map((s) => (
        <button
          key={s}
          type="button"
          disabled={saving}
          onClick={async () => {
            if (s === value) return;
            setSaving(true);
            try {
              await onChange(s);
            } finally {
              setSaving(false);
            }
          }}
          className={`rounded-full px-3 py-1 text-xs font-medium transition-all ${
            value === s
              ? `${LEAD_STAGE_COLORS[s]} ring-2 ring-offset-1 ring-current`
              : 'bg-gray-100 text-text-secondary hover:bg-gray-200'
          }`}
        >
          {LEAD_STAGE_LABELS[s]}
        </button>
      ))}
    </div>
  );
}

function TagsEditor({
  tags,
  onChange,
}: {
  tags: string[];
  onChange?: (tags: string[]) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [search, setSearch] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { data: allTags } = useTags();

  const filteredTags = useMemo(
    () =>
      (allTags ?? [])
        .filter((t) => !tags.includes(t.name))
        .filter((t) => search ? t.name.toLowerCase().includes(search.toLowerCase()) : false),
    [allTags, tags, search],
  );

  const addTag = useCallback(async (name: string) => {
    if (!onChange || tags.includes(name)) return;
    const newTags = [...tags, name];
    setSaving(true);
    try {
      await onChange(newTags);
    } finally {
      setSaving(false);
    }
  }, [onChange, tags]);

  const removeTag = useCallback(async (name: string) => {
    if (!onChange) return;
    const newTags = tags.filter((t) => t !== name);
    setSaving(true);
    try {
      await onChange(newTags);
    } finally {
      setSaving(false);
    }
  }, [onChange, tags]);

  // Close dropdown on click outside
  useEffect(() => {
    if (!editing) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setEditing(false);
        setDropdownOpen(false);
        setSearch('');
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [editing]);

  if (!onChange) {
    if (tags.length === 0) return null;
    return (
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag) => (
          <Badge key={tag} variant="gray">{tag}</Badge>
        ))}
      </div>
    );
  }

  return (
    <div ref={containerRef}>
      <div className="flex flex-wrap gap-1.5 mb-1">
        {tags.map((tag) => (
          <span
            key={tag}
            title={tag}
            className="inline-flex items-center gap-1 rounded-full bg-slate-100 text-slate-700 px-2.5 py-0.5 text-xs font-medium"
          >
            {tag.includes('/') ? tag.split('/').pop() : tag}
            <button
              type="button"
              onClick={() => removeTag(tag)}
              className="hover:text-red-500"
              disabled={saving}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>

      {editing ? (
        <div className="relative">
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setDropdownOpen(true);
            }}
            onFocus={() => { if (search) setDropdownOpen(true); }}
            placeholder="Zoek of typ een tag..."
            className="w-full rounded-lg border border-primary-300 px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter' && search.trim()) {
                e.preventDefault();
                addTag(search.trim());
                setSearch('');
                setDropdownOpen(false);
              } else if (e.key === 'Escape') {
                setEditing(false);
                setSearch('');
                setDropdownOpen(false);
              }
            }}
          />
          {dropdownOpen && search && filteredTags.length > 0 && (
            <div className="absolute z-10 mt-1 w-full bg-white border border-border rounded-lg shadow-lg max-h-40 overflow-y-auto">
              {filteredTags.slice(0, 10).map((tag) => (
                <button
                  key={tag.id}
                  type="button"
                  onClick={() => {
                    addTag(tag.name);
                    setSearch('');
                    setDropdownOpen(false);
                  }}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition-colors"
                >
                  {tag.name}
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-xs text-text-secondary hover:text-primary-600 transition-colors"
        >
          + Tag toevoegen
        </button>
      )}
    </div>
  );
}

export function LeadContentLayout({
  title,
  stage,
  description,
  organization,
  assigneeId,
  assigneeName,
  broughtById,
  broughtByName,
  initiatiefId,
  initiatiefName,
  initiatiefKleur,
  nextAction,
  nextActionDate,
  createdAt,
  tags,
  onTitleChange,
  onStageChange,
  onDescriptionChange,
  onOrganizationChange,
  onAssigneeChange,
  onBroughtByChange,
  onInitiatiefChange,
  onNextActionChange,
  onNextActionDateChange,
  onTagsChange,
  onCreatedAtChange,
  rightColumnChildren,
  bottomChildren,
}: LeadContentLayoutProps) {
  const { data: people } = usePeople();
  const { data: initiatieven } = useInitiatieven();
  const createInitiatief = useCreateInitiatief();
  const { currentPerson } = useCurrentPerson();

  const overdue = nextActionDate && isOverdue(nextActionDate);

  const personOptions = useMemo(
    () => buildPersonOptions(people ?? [], currentPerson, (p) => ({
      value: p.id,
      label: p.naam,
      description: formatFunctie(p.functie),
    })),
    [people, currentPerson],
  );

  const initiatiefOptions = useMemo(
    () => [
      { value: '', label: 'Geen initiatief' },
      ...(initiatieven?.map((i) => ({ value: i.id, label: i.naam })) ?? []),
    ],
    [initiatieven],
  );

  return (
    <div className="space-y-5">
      {/* Title */}
      {onTitleChange ? (
        <InlineEditableField
          type="text"
          value={title}
          onSave={async (v) => { if (v) await onTitleChange(v); }}
          displayValue={<span className="text-lg font-semibold text-text">{title}</span>}
          placeholder="Titel van de lead"
        />
      ) : (
        <h2 className="text-lg font-semibold text-text">{title}</h2>
      )}

      {/* Stage */}
      <div className="flex items-center gap-2 flex-wrap">
        <StagePills value={stage} onChange={onStageChange} />
        {nextActionDate && !onStageChange && (
          <span className={`inline-flex items-center gap-1 text-sm ${overdue ? 'text-red-600 font-medium bg-red-50 rounded-md px-2 py-0.5' : 'text-text-secondary'}`}>
            <Calendar className="h-4 w-4" />
            {formatDateLong(nextActionDate)}
          </span>
        )}
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
        {/* LEFT COLUMN */}
        <div className="space-y-4">
          {/* Description */}
          {onDescriptionChange ? (
            <InlineEditableField
              type="richtext"
              label="Beschrijving"
              value={description}
              onSave={onDescriptionChange}
              displayValue={
                description ? (
                  <div className="text-sm text-text">
                    <RichTextDisplay content={description} />
                  </div>
                ) : undefined
              }
              placeholder="Voeg een beschrijving toe..."
              rows={5}
            />
          ) : description ? (
            <div>
              <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Beschrijving
              </h4>
              <div className="text-sm text-text">
                <RichTextDisplay content={description} />
              </div>
            </div>
          ) : null}

          {/* Metadata fields */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            {/* Organization */}
            <div>
              {onOrganizationChange ? (
                <InlineEditableField
                  type="text"
                  label="Organisatie"
                  value={organization}
                  onSave={onOrganizationChange}
                  placeholder="Naam van de organisatie"
                />
              ) : (
                <>
                  <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                    Organisatie
                  </h4>
                  <span className="text-text-secondary">{organization ?? 'Onbekend'}</span>
                </>
              )}
            </div>

            {/* Initiatief */}
            <div>
              {onInitiatiefChange ? (
                <InlineEditableField
                  type="select"
                  label="Initiatief"
                  value={initiatiefId}
                  onSave={async (v) => onInitiatiefChange(v)}
                  displayValue={
                    initiatiefName ? (
                      <span
                        className="inline-block rounded-full px-2 py-0.5 text-xs font-medium text-white"
                        style={{ backgroundColor: initiatiefKleur || '#6B7280' }}
                      >
                        {initiatiefName}
                      </span>
                    ) : undefined
                  }
                  options={initiatiefOptions}
                  placeholder="Selecteer initiatief..."
                  clearable={!!initiatiefId}
                  onCreate={async (name) => {
                    const kleur = INITIATIEF_COLORS[Math.floor(Math.random() * INITIATIEF_COLORS.length)];
                    const result = await createInitiatief.mutateAsync({ naam: name, kleur });
                    return result.id;
                  }}
                  createLabel="Nieuw initiatief"
                />
              ) : initiatiefName ? (
                <>
                  <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                    Initiatief
                  </h4>
                  <span
                    className="inline-block rounded-full px-2 py-0.5 text-xs font-medium text-white"
                    style={{ backgroundColor: initiatiefKleur || '#6B7280' }}
                  >
                    {initiatiefName}
                  </span>
                </>
              ) : null}
            </div>
          </div>

          {/* Next action + date */}
          {(onNextActionChange || nextAction) && (
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                {onNextActionChange ? (
                  <InlineEditableField
                    type="text"
                    label="Volgende actie"
                    value={nextAction}
                    onSave={onNextActionChange}
                    placeholder="Beschrijf de volgende actie..."
                  />
                ) : (
                  <>
                    <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                      Volgende actie
                    </h4>
                    <span className="text-text-secondary">{nextAction ?? '-'}</span>
                  </>
                )}
              </div>
              <div>
                {onNextActionDateChange ? (
                  <InlineEditableField
                    type="date"
                    label="Actiedatum"
                    value={nextActionDate}
                    onSave={onNextActionDateChange}
                    displayValue={
                      nextActionDate ? (
                        <span className={`inline-flex items-center gap-1 ${overdue ? 'text-red-600 font-medium' : 'text-text-secondary'}`}>
                          <Calendar className="h-4 w-4" />
                          {formatDateLong(nextActionDate)}
                        </span>
                      ) : undefined
                    }
                    placeholder="Kies een datum..."
                  />
                ) : nextActionDate ? (
                  <>
                    <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                      Actiedatum
                    </h4>
                    <span className={`inline-flex items-center gap-1 ${overdue ? 'text-red-600 font-medium' : 'text-text-secondary'}`}>
                      <Calendar className="h-4 w-4" />
                      {formatDateLong(nextActionDate)}
                    </span>
                  </>
                ) : null}
              </div>
            </div>
          )}

          {/* Tags */}
          <div>
            <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
              Tags
            </h4>
            <TagsEditor tags={tags} onChange={onTagsChange} />
          </div>

          {/* Created at */}
          {(onCreatedAtChange || createdAt) && (
            <div className="text-sm">
              {onCreatedAtChange ? (
                <InlineEditableField
                  type="date"
                  label="Datum"
                  value={createdAt}
                  onSave={onCreatedAtChange}
                  displayValue={
                    createdAt ? (
                      <span className="inline-flex items-center gap-1.5 text-text-secondary">
                        <Calendar className="h-4 w-4" />
                        {formatDateLong(createdAt)}
                      </span>
                    ) : undefined
                  }
                  placeholder="Kies een datum..."
                />
              ) : (
                <>
                  <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                    Aangemaakt
                  </h4>
                  <span className="inline-flex items-center gap-1.5 text-text-secondary">
                    <Calendar className="h-4 w-4" />
                    {formatDateLong(createdAt!)}
                  </span>
                </>
              )}
            </div>
          )}
        </div>

        {/* RIGHT COLUMN */}
        <div className="space-y-4">
          {/* Toegewezen aan */}
          <div>
            {onAssigneeChange ? (
              <InlineEditableField
                type="select"
                label="Toegewezen aan"
                value={assigneeId}
                onSave={async (v) => onAssigneeChange(v)}
                displayValue={
                  assigneeName ? (
                    <span className="inline-flex items-center gap-1.5 text-text">
                      <User className="h-4 w-4 text-text-secondary" />
                      {assigneeName}
                    </span>
                  ) : undefined
                }
                options={[
                  { value: '', label: 'Niet toegewezen' },
                  ...personOptions,
                ]}
                placeholder="Zoek een persoon..."
                clearable={!!assigneeId}
                onCreate={async (name) => {
                  const result = await createPerson({ naam: name }, true);
                  return result?.id ?? null;
                }}
                createLabel="Nieuwe persoon aanmaken"
              />
            ) : (
              <>
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                  Toegewezen aan
                </h4>
                {assigneeName ? (
                  <span className="inline-flex items-center gap-1.5 text-text">
                    <User className="h-4 w-4 text-text-secondary" />
                    {assigneeName}
                  </span>
                ) : (
                  <span className="text-text-secondary">Niet toegewezen</span>
                )}
              </>
            )}
          </div>

          {/* Binnengebracht door */}
          <div>
            {onBroughtByChange ? (
              <InlineEditableField
                type="select"
                label="Binnengebracht door"
                value={broughtById}
                onSave={async (v) => onBroughtByChange(v)}
                displayValue={
                  broughtByName ? (
                    <span className="inline-flex items-center gap-1.5 text-text">
                      <User className="h-4 w-4 text-text-secondary" />
                      {broughtByName}
                    </span>
                  ) : undefined
                }
                options={personOptions}
                placeholder="Zoek een teamlid..."
                clearable={!!broughtById}
              />
            ) : (
              <>
                <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                  Binnengebracht door
                </h4>
                {broughtByName ? (
                  <span className="inline-flex items-center gap-1.5 text-text">
                    <User className="h-4 w-4 text-text-secondary" />
                    {broughtByName}
                  </span>
                ) : (
                  <span className="text-text-secondary">Onbekend</span>
                )}
              </>
            )}
          </div>

          {/* Context-specific right column content */}
          {rightColumnChildren}
        </div>
      </div>

      {/* Full-width bottom sections */}
      {bottomChildren}
    </div>
  );
}
