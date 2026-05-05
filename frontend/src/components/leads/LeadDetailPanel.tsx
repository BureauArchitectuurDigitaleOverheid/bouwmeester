import { useState, useMemo, useRef, useEffect } from 'react';
import {
  Trash2,
  Pencil,
  User,
  Calendar,
  Paperclip,
  Download,
  X,
  Plus,
  Link as LinkIcon,
  MessageSquare,
  Phone,
  Mail,
  FileText,
  Upload,
  ZoomIn,
} from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { LinkLeadNodeModal } from './LinkLeadNodeModal';
import { createPerson } from '@/api/people';
import { Badge } from '@/components/common/Badge';
import { DetailSection } from '@/components/common/DetailSection';
import { DetailMetadataGrid } from '@/components/common/DetailMetadataGrid';
import { DetailModalFooter } from '@/components/common/DetailModalFooter';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import {
  useLead,
  useUpdateLead,
  useDeleteLead,
  useCreateLeadActivity,
  useAddLeadContact,
  useRemoveLeadContact,
  useUnlinkLeadNode,
  useUploadLeadAttachment,
  useDeleteLeadAttachment,
  useLeadTags,
  useAddTagToLead,
  useRemoveTagFromLead,
} from '@/hooks/useLeads';
import { usePeople } from '@/hooks/usePeople';
import { useInitiatieven, useCreateInitiatief } from '@/hooks/useInitiatieven';
import { getLeadAttachmentDownloadUrl } from '@/api/leads';
import { isOverdue, formatDateLong, timeAgo } from '@/utils/dates';
import {
  LeadStage,
  LEAD_STAGE_LABELS,
  LEAD_STAGE_COLORS,
  LEAD_STAGE_ORDER,
  LeadActivityType,
  LEAD_ACTIVITY_TYPE_LABELS,
  INITIATIEF_COLORS,
  LEAD_CONTACT_ROL_LABELS,
  ENGAGEMENT_TYPE_LABELS,
} from '@/types';
import type { LeadUpdate, LeadActivityCreate, EngagementType } from '@/types';

interface LeadDetailPanelProps {
  leadId: string | null;
  open: boolean;
  onClose: () => void;
  zIndex?: number;
}

const ACTIVITY_ICONS: Record<LeadActivityType, React.ReactNode> = {
  [LeadActivityType.NOTE]: <MessageSquare className="h-3.5 w-3.5" />,
  [LeadActivityType.STAGE_CHANGE]: <FileText className="h-3.5 w-3.5" />,
  [LeadActivityType.MEETING]: <User className="h-3.5 w-3.5" />,
  [LeadActivityType.CALL]: <Phone className="h-3.5 w-3.5" />,
  [LeadActivityType.EMAIL]: <Mail className="h-3.5 w-3.5" />,
  [LeadActivityType.EVALUATIE]: <FileText className="h-3.5 w-3.5" />,
};

export function LeadDetailPanel({ leadId, open, onClose, zIndex }: LeadDetailPanelProps) {
  const { data: lead, isLoading } = useLead(leadId);
  const { data: people } = usePeople();
  const { data: initiatieven } = useInitiatieven();
  const createInitiatief = useCreateInitiatief();

  const contactPersonOptions = useMemo(
    () => (people ?? [])
      .filter((p) => p.is_active)
      .sort((a, b) => a.naam.localeCompare(b.naam))
      .map((p) => ({ value: p.id, label: p.naam })),
    [people],
  );

  const updateLead = useUpdateLead();
  const deleteLead = useDeleteLead();
  const createActivity = useCreateLeadActivity();
  const addContact = useAddLeadContact();
  const removeContact = useRemoveLeadContact();
  const unlinkNode = useUnlinkLeadNode();
  const uploadAttachment = useUploadLeadAttachment();
  const deleteAttachment = useDeleteLeadAttachment();
  const { data: leadTags } = useLeadTags(leadId);
  const addTagToLead = useAddTagToLead();
  const removeTagFromLead = useRemoveTagFromLead();

  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editOrganization, setEditOrganization] = useState('');
  const [editStage, setEditStage] = useState<LeadStage>(LeadStage.VERKENNEN);
  const [editAssignee, setEditAssignee] = useState('');
  const [editNextAction, setEditNextAction] = useState('');
  const [editNextActionDate, setEditNextActionDate] = useState('');
  const [editInitiatiefId, setEditInitiatiefId] = useState('');
  const [editTags, setEditTags] = useState('');
  const [editEngagementType, setEditEngagementType] = useState<EngagementType | ''>('');
  const [editScoreStrategisch, setEditScoreStrategisch] = useState<number | ''>('');
  const [editScorePolitiek, setEditScorePolitiek] = useState<number | ''>('');
  const [editScorePositie, setEditScorePositie] = useState<number | ''>('');

  // Activity form
  const [activityContent, setActivityContent] = useState('');
  const [activityType, setActivityType] = useState<LeadActivityType>(LeadActivityType.NOTE);
  const [activityUitkomst, setActivityUitkomst] = useState('');
  const [activityVervolgacties, setActivityVervolgacties] = useState('');

  // Contact add form
  const [showAddContact, setShowAddContact] = useState(false);
  const [contactPersonId, setContactPersonId] = useState('');
  const [contactRol, setContactRol] = useState('contactpersoon');

  // Node link modal
  const [showLinkNode, setShowLinkNode] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [lightboxSrc, setLightboxSrc] = useState<{ src: string; alt: string } | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  useEffect(() => {
    if (!lightboxSrc) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLightboxSrc(null);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [lightboxSrc]);

  if (!open) return null;

  const startEditing = () => {
    if (!lead) return;
    setEditTitle(lead.title);
    setEditDescription(lead.description ?? '');
    setEditOrganization(lead.organization ?? '');
    setEditStage(lead.stage);
    setEditAssignee(lead.assignee_id ?? '');
    setEditNextAction(lead.next_action ?? '');
    setEditNextActionDate(lead.next_action_date ?? '');
    setEditInitiatiefId(lead.initiatief_id ?? '');
    setEditTags((leadTags ?? []).map((lt) => lt.tag.name).join(', '));
    setEditEngagementType(lead.engagement_type ?? '');
    setEditScoreStrategisch(lead.score_strategisch ?? '');
    setEditScorePolitiek(lead.score_politiek ?? '');
    setEditScorePositie(lead.score_positie ?? '');
    setEditing(true);
  };

  const saveEdit = async () => {
    if (!lead) return;
    const tagList = editTags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const data: LeadUpdate = {
      title: editTitle.trim(),
      description: editDescription.trim() || null,
      organization: editOrganization.trim() || null,
      stage: editStage,
      assignee_id: editAssignee || null,
      next_action: editNextAction.trim() || null,
      next_action_date: editNextActionDate || null,
      initiatief_id: editInitiatiefId || null,
      engagement_type: editEngagementType || null,
      score_strategisch: editScoreStrategisch === '' ? null : editScoreStrategisch,
      score_politiek: editScorePolitiek === '' ? null : editScorePolitiek,
      score_positie: editScorePositie === '' ? null : editScorePositie,
    };

    // Update lead fields
    updateLead.mutate(
      { id: lead.id, data },
      {
        onSuccess: async () => {
          // Sync tags: remove tags not in the new list, add new ones
          const currentTagNames = (leadTags ?? []).map((lt) => lt.tag.name);
          const toRemove = (leadTags ?? []).filter((lt) => !tagList.includes(lt.tag.name));
          const toAdd = tagList.filter((name) => !currentTagNames.includes(name));

          for (const lt of toRemove) {
            try {
              await removeTagFromLead.mutateAsync({ leadId: lead.id, tagId: lt.tag.id });
            } catch {
              // Non-critical
            }
          }
          for (const name of toAdd) {
            try {
              await addTagToLead.mutateAsync({ leadId: lead.id, data: { tag_name: name } });
            } catch {
              // Non-critical
            }
          }
          setEditing(false);
        },
      },
    );
  };

  const handleDelete = () => {
    if (!lead) return;
    setShowDeleteConfirm(true);
  };

  const isActivityEmpty = (() => {
    if (!activityContent) return true;
    try {
      const doc = JSON.parse(activityContent);
      if (doc?.type !== 'doc') return !activityContent.trim();
      const hasContent = doc.content?.some((node: { type: string; content?: unknown[] }) =>
        node.content && node.content.length > 0,
      );
      return !hasContent;
    } catch {
      return !activityContent.trim();
    }
  })();

  const handleAddActivity = () => {
    if (!lead || isActivityEmpty) return;
    const data: LeadActivityCreate = {
      content: activityContent,
      activity_type: activityType,
      uitkomst:
        activityType === LeadActivityType.EVALUATIE
          ? activityUitkomst.trim() || null
          : null,
      vervolgacties:
        activityType === LeadActivityType.EVALUATIE
          ? activityVervolgacties.trim() || null
          : null,
    };
    createActivity.mutate(
      { leadId: lead.id, data },
      {
        onSuccess: () => {
          setActivityContent('');
          setActivityType(LeadActivityType.NOTE);
          setActivityUitkomst('');
          setActivityVervolgacties('');
        },
      },
    );
  };

  const handleAddContact = () => {
    if (!lead || !contactPersonId) return;
    addContact.mutate(
      { leadId: lead.id, personId: contactPersonId, rol: contactRol },
      {
        onSuccess: () => {
          setShowAddContact(false);
          setContactPersonId('');
          setContactRol('contactpersoon');
        },
      },
    );
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!lead || !e.target.files) return;
    for (const file of Array.from(e.target.files)) {
      uploadAttachment.mutate({ leadId: lead.id, file });
    }
    e.target.value = '';
  };

  const overdue = lead?.next_action_date && isOverdue(lead.next_action_date);

  return (
    <>
    <Modal
      open={open}
      onClose={onClose}
      title={isLoading ? 'Laden...' : lead?.title ?? 'Lead niet gevonden'}
      size="lg"
      zIndex={zIndex}
      entityLabel="Lead"
      footer={
        editing ? (
          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(false)}>Annuleren</Button>
            <Button onClick={saveEdit} loading={updateLead.isPending}>Opslaan</Button>
          </div>
        ) : (
          <DetailModalFooter
            onClose={onClose}
            actions={
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<Pencil className="h-4 w-4" />}
                  onClick={startEditing}
                  disabled={!lead}
                >
                  Bewerken
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  icon={<Trash2 className="h-4 w-4" />}
                  onClick={handleDelete}
                  disabled={!lead}
                >
                  Verwijderen
                </Button>
              </div>
            }
          />
        )
      }
    >
      {isLoading ? (
        <LoadingSpinner className="py-8" />
      ) : !lead ? (
        <div className="flex items-center justify-center py-8 text-text-secondary text-sm">
          Lead niet gevonden.
        </div>
      ) : editing ? (
        /* Edit mode */
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text mb-1">Titel</label>
            <input
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <CreatableSelect
                label="Stage"
                value={editStage}
                onChange={(v) => setEditStage(v as LeadStage)}
                options={LEAD_STAGE_ORDER.map((s) => ({
                  value: s,
                  label: LEAD_STAGE_LABELS[s],
                }))}
                placeholder="Selecteer stage..."
                searchable={false}
              />
            </div>
            <div>
              <CreatableSelect
                label="Toegewezen aan"
                value={editAssignee}
                onChange={setEditAssignee}
                options={[
                  { value: '', label: 'Niet toegewezen' },
                  ...(people?.map((p) => ({
                    value: p.id,
                    label: p.naam,
                    description: p.functie ?? undefined,
                  })) ?? []),
                ]}
                placeholder="Zoek een persoon..."
                onCreate={async (name) => {
                  const result = await createPerson({ naam: name }, true);
                  return result?.id ?? null;
                }}
                createLabel="Nieuwe persoon aanmaken"
                onClear={editAssignee ? () => setEditAssignee('') : undefined}
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-text mb-1">Organisatie</label>
            <input
              type="text"
              value={editOrganization}
              onChange={(e) => setEditOrganization(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
            />
          </div>
          <div>
            <CreatableSelect
              label="Initiatief"
              value={editInitiatiefId}
              onChange={setEditInitiatiefId}
              options={[
                { value: '', label: 'Geen initiatief' },
                ...(initiatieven?.map((i) => ({ value: i.id, label: i.naam })) ?? []),
              ]}
              placeholder="Selecteer initiatief..."
              onClear={editInitiatiefId ? () => setEditInitiatiefId('') : undefined}
              onCreate={async (name) => {
                const kleur = INITIATIEF_COLORS[Math.floor(Math.random() * INITIATIEF_COLORS.length)];
                const result = await createInitiatief.mutateAsync({ naam: name, kleur });
                return result.id;
              }}
              createLabel="Nieuw initiatief"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text mb-1">Volgende actie</label>
            <input
              type="text"
              value={editNextAction}
              onChange={(e) => setEditNextAction(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text mb-1">Actiedatum</label>
            <input
              type="date"
              value={editNextActionDate}
              onChange={(e) => setEditNextActionDate(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text mb-1">Tags</label>
            <input
              type="text"
              value={editTags}
              onChange={(e) => setEditTags(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
              placeholder="Komma-gescheiden tags"
            />
          </div>
          {(() => {
            const selectedInit = initiatieven?.find((i) => i.id === editInitiatiefId);
            if (!selectedInit?.funnel_enabled) return null;
            const labelStrategisch =
              selectedInit.score_strategisch_label || 'Strategisch belang';
            const labelPolitiek =
              selectedInit.score_politiek_label || 'Politiek belang';
            const labelPositie =
              selectedInit.score_positie_label || 'Positie / omgeving';
            return (
              <div className="space-y-3 rounded-lg border border-border p-3 bg-gray-50/50">
                <div className="text-xs text-text-secondary uppercase tracking-wider font-semibold">
                  Funnel-afweging
                </div>
                <div>
                  <label className="block text-sm font-medium text-text mb-1">
                    Engagement type
                  </label>
                  <select
                    value={editEngagementType}
                    onChange={(e) =>
                      setEditEngagementType(
                        (e.target.value || '') as EngagementType | '',
                      )
                    }
                    className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-white focus:outline-none focus:border-primary-400"
                  >
                    <option value="">—</option>
                    {(
                      Object.keys(ENGAGEMENT_TYPE_LABELS) as EngagementType[]
                    ).map((k) => (
                      <option key={k} value={k}>
                        {ENGAGEMENT_TYPE_LABELS[k]}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {(
                    [
                      [labelStrategisch, editScoreStrategisch, setEditScoreStrategisch],
                      [labelPolitiek, editScorePolitiek, setEditScorePolitiek],
                      [labelPositie, editScorePositie, setEditScorePositie],
                    ] as const
                  ).map(([label, value, setter], idx) => (
                    <label key={idx} className="flex flex-col gap-0.5">
                      <span className="text-xs text-text-secondary">{label}</span>
                      <select
                        value={value}
                        onChange={(e) =>
                          setter(
                            e.target.value === '' ? '' : Number(e.target.value),
                          )
                        }
                        className="text-sm rounded-lg border border-border px-2 py-1 bg-white"
                      >
                        <option value="">—</option>
                        {[1, 2, 3, 4, 5].map((n) => (
                          <option key={n} value={n}>
                            {n}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
              </div>
            );
          })()}
          <RichTextFormField
            label="Beschrijving"
            value={editDescription}
            onChange={setEditDescription}
            rows={5}
          />
        </div>
      ) : (
        /* View mode */
        <div className="space-y-5">
          {/* Stage badge + next action */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${LEAD_STAGE_COLORS[lead.stage]}`}>
              {LEAD_STAGE_LABELS[lead.stage]}
            </span>
            {lead.next_action_date && (
              <span className={`inline-flex items-center gap-1 text-sm ${overdue ? 'text-red-600 font-medium bg-red-50 rounded-md px-2 py-0.5' : 'text-text-secondary'}`}>
                <Calendar className="h-4 w-4" />
                {formatDateLong(lead.next_action_date)}
              </span>
            )}
          </div>

          {/* Description */}
          {lead.description && (
            <DetailSection title="Beschrijving">
              <div className="text-sm text-text">
                <RichTextDisplay content={lead.description} />
              </div>
            </DetailSection>
          )}

          {/* Metadata */}
          <DetailMetadataGrid
            items={[
              {
                label: 'Organisatie',
                value: lead.externe_organisatie?.naam ?? lead.organization ?? 'Onbekend',
              },
              {
                label: 'Toegewezen aan',
                value: lead.assignee ? (
                  <span className="inline-flex items-center gap-1.5 text-text">
                    <User className="h-4 w-4 text-text-secondary" />
                    {lead.assignee.naam}
                  </span>
                ) : (
                  <span className="text-text-secondary">Niet toegewezen</span>
                ),
              },
              {
                label: 'Binnengebracht door',
                value: lead.brought_by ? (
                  <span className="inline-flex items-center gap-1.5 text-text">
                    <User className="h-4 w-4 text-text-secondary" />
                    {lead.brought_by.naam}
                  </span>
                ) : (
                  <span className="text-text-secondary">Onbekend</span>
                ),
              },
              {
                label: 'Initiatief',
                value: lead.initiatief ? (
                  <span
                    className="inline-block rounded-full px-2 py-0.5 text-xs font-medium text-white"
                    style={{ backgroundColor: lead.initiatief.kleur || '#6B7280' }}
                  >
                    {lead.initiatief.naam}
                  </span>
                ) : (
                  '-'
                ),
              },
              {
                label: 'Volgende actie',
                value: lead.next_action ?? '-',
              },
              {
                label: 'Aangemaakt',
                value: formatDateLong(lead.created_at),
                icon: <Calendar className="h-4 w-4" />,
              },
            ]}
          />

          {/* Funnel-afweging (only when initiatief has funnel_enabled) */}
          {(() => {
            const linkedInit = initiatieven?.find(
              (i) => i.id === lead.initiatief_id,
            );
            if (!linkedInit?.funnel_enabled) return null;
            const hasAny =
              lead.engagement_type ||
              lead.score_strategisch != null ||
              lead.score_politiek != null ||
              lead.score_positie != null;
            if (!hasAny) return null;
            const labels = [
              [linkedInit.score_strategisch_label || 'Strategisch belang', lead.score_strategisch],
              [linkedInit.score_politiek_label || 'Politiek belang', lead.score_politiek],
              [linkedInit.score_positie_label || 'Positie / omgeving', lead.score_positie],
            ] as const;
            return (
              <DetailSection title="Funnel-afweging">
                <div className="space-y-2">
                  {lead.engagement_type && (
                    <div className="text-sm">
                      <span className="text-text-secondary">Engagement: </span>
                      <span className="text-text font-medium">
                        {ENGAGEMENT_TYPE_LABELS[lead.engagement_type]}
                      </span>
                    </div>
                  )}
                  <div className="grid grid-cols-3 gap-2 text-sm">
                    {labels.map(([label, value], idx) => (
                      <div key={idx} className="text-text">
                        <div className="text-xs text-text-secondary">{label}</div>
                        <div className="font-medium">
                          {value != null ? `${value}/5` : '—'}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </DetailSection>
            );
          })()}

          {/* Tags */}
          {(leadTags ?? []).length > 0 && (
            <DetailSection title="Tags">
              <div className="flex flex-wrap gap-1.5">
                {(leadTags ?? []).map((lt) => (
                  <Badge key={lt.id} variant="gray">{lt.tag.name}</Badge>
                ))}
              </div>
            </DetailSection>
          )}

          {/* Bijlagen */}
          <DetailSection
            title="Bijlagen"
            icon={<Paperclip className="h-3.5 w-3.5" />}
            count={lead.attachments.length}
            separated
            action={
              <label className="cursor-pointer">
                <input
                  type="file"
                  multiple
                  className="hidden"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Upload className="h-3.5 w-3.5" />}
                  onClick={() => fileInputRef.current?.click()}
                >
                  Uploaden
                </Button>
              </label>
            }
          >
            {lead.attachments.length > 0 ? (
              <div className="space-y-1">
                {lead.attachments.map((att) => (
                  <div key={att.id}>
                    <div className={`flex items-center gap-2 text-sm rounded-lg px-2 py-1.5 hover:bg-gray-50 ${!att.bestand_beschikbaar ? 'opacity-50' : ''}`}>
                      <Paperclip className="h-3.5 w-3.5 text-text-secondary shrink-0" />
                      <span className="flex-1 truncate text-text">{att.bestandsnaam}</span>
                      {!att.bestand_beschikbaar ? (
                        <span className="text-xs text-red-500">Bestand niet beschikbaar</span>
                      ) : (
                        <>
                          <span className="text-xs text-text-secondary">{Math.round(att.bestandsgrootte / 1024)} KB</span>
                          <a
                            href={getLeadAttachmentDownloadUrl(lead.id, att.id)}
                            className="p-1 text-text-secondary hover:text-primary-600 transition-colors"
                            title="Downloaden"
                          >
                            <Download className="h-3.5 w-3.5" />
                          </a>
                        </>
                      )}
                      <button
                        onClick={() => deleteAttachment.mutate({ leadId: lead.id, attachmentId: att.id })}
                        className="p-1 text-text-secondary hover:text-red-500 transition-colors"
                        title="Verwijderen"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    {att.bestand_beschikbaar && att.content_type?.startsWith('image/') && (
                      <button
                        onClick={() => setLightboxSrc({
                          src: getLeadAttachmentDownloadUrl(lead.id, att.id),
                          alt: att.bestandsnaam,
                        })}
                        className="relative group mt-2 ml-2 block"
                      >
                        <img
                          src={getLeadAttachmentDownloadUrl(lead.id, att.id)}
                          alt={att.bestandsnaam}
                          className="rounded-lg border border-border max-h-48 object-contain"
                        />
                        <div className="absolute inset-0 rounded-lg bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
                          <ZoomIn className="h-6 w-6 text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow-md" />
                        </div>
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-text-secondary">Geen bijlagen</p>
            )}
          </DetailSection>

          {/* Contactpersonen */}
          <DetailSection
            title="Contactpersonen"
            icon={<User className="h-3.5 w-3.5" />}
            count={lead.contacts.length}
            separated
            action={
              <Button
                variant="ghost"
                size="sm"
                icon={<Plus className="h-3.5 w-3.5" />}
                onClick={() => setShowAddContact(true)}
              >
                Toevoegen
              </Button>
            }
          >
            {lead.contacts.length > 0 ? (
              <div className="space-y-1">
                {lead.contacts.map((contact) => (
                  <div key={contact.id} className="flex items-center gap-2 text-sm rounded-lg px-2 py-1.5 hover:bg-gray-50">
                    <User className="h-3.5 w-3.5 text-text-secondary shrink-0" />
                    <span className="flex-1 text-text">{contact.person_naam}</span>
                    <Badge variant="gray">{LEAD_CONTACT_ROL_LABELS[contact.rol] ?? contact.rol}</Badge>
                    <button
                      onClick={() => removeContact.mutate({ leadId: lead.id, contactId: contact.id })}
                      className="p-1 text-text-secondary hover:text-red-500 transition-colors"
                      title="Verwijderen"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-text-secondary">Geen contactpersonen</p>
            )}

            {showAddContact && (
              <div className="space-y-2 mt-2">
                <div className="flex items-end gap-2">
                  <div className="flex-1">
                    <CreatableSelect
                      value={contactPersonId}
                      onChange={setContactPersonId}
                      options={contactPersonOptions}
                      placeholder="Zoek of typ een naam..."
                      onCreate={async (name) => {
                        const newPerson = await createPerson({ naam: name }, true);
                        return newPerson.id;
                      }}
                      createLabel="Nieuw contact"
                    />
                  </div>
                  <input
                    type="text"
                    value={contactRol}
                    onChange={(e) => setContactRol(e.target.value)}
                    placeholder="Rol"
                    className="w-32 rounded-lg border border-border px-2 py-1.5 text-sm focus:outline-none focus:border-primary-400"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={handleAddContact} disabled={!contactPersonId}>
                    Toevoegen
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setShowAddContact(false)}>
                    Annuleren
                  </Button>
                </div>
              </div>
            )}
          </DetailSection>

          {/* Gelinkte nodes */}
          <DetailSection
            title="Gelinkte nodes"
            icon={<LinkIcon className="h-3.5 w-3.5" />}
            count={lead.linked_nodes.length}
            separated
            action={
              <Button
                variant="ghost"
                size="sm"
                icon={<Plus className="h-3.5 w-3.5" />}
                onClick={() => setShowLinkNode(true)}
              >
                Koppelen
              </Button>
            }
          >
            {lead.linked_nodes.length > 0 ? (
              <div className="space-y-1">
                {lead.linked_nodes.map((ln) => (
                  <div key={ln.id} className="flex items-center gap-2 text-sm rounded-lg px-2 py-1.5 hover:bg-gray-50">
                    <LinkIcon className="h-3.5 w-3.5 text-text-secondary shrink-0" />
                    <span className="flex-1 text-text">{ln.node_title}</span>
                    <Badge variant="gray">{ln.node_type}</Badge>
                    <button
                      onClick={() => unlinkNode.mutate({ leadId: lead.id, linkId: ln.id })}
                      className="p-1 text-text-secondary hover:text-red-500 transition-colors"
                      title="Ontkoppelen"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-text-secondary">Geen gelinkte nodes</p>
            )}
          </DetailSection>

          {/* Activiteiten */}
          <DetailSection
            title="Activiteiten"
            icon={<MessageSquare className="h-3.5 w-3.5" />}
            count={lead.activities.length}
            separated
          >
            {/* Add activity form */}
            <div className="space-y-2 mb-4">
              <RichTextEditor
                value={activityContent}
                onChange={setActivityContent}
                placeholder="Voeg een notitie of activiteit toe... Gebruik @ voor personen, # voor nodes/taken"
                rows={2}
              />
              {activityType === LeadActivityType.EVALUATIE && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <textarea
                    value={activityUitkomst}
                    onChange={(e) => setActivityUitkomst(e.target.value)}
                    placeholder="Uitkomst van de evaluatie..."
                    rows={2}
                    className="text-sm rounded-lg border border-border px-2 py-1 focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                  <textarea
                    value={activityVervolgacties}
                    onChange={(e) => setActivityVervolgacties(e.target.value)}
                    placeholder="Vervolgacties / wat moet er nu gebeuren..."
                    rows={2}
                    className="text-sm rounded-lg border border-border px-2 py-1 focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
              )}
              <div className="flex items-center gap-2">
                <div className="w-36">
                  <CreatableSelect
                    value={activityType}
                    onChange={(v) => setActivityType(v as LeadActivityType)}
                    options={Object.entries(LEAD_ACTIVITY_TYPE_LABELS)
                      .filter(([value]) => value !== LeadActivityType.STAGE_CHANGE)
                      .map(([value, label]) => ({ value, label }))}
                    placeholder="Type..."
                    searchable={false}
                  />
                </div>
                <Button
                  size="sm"
                  onClick={handleAddActivity}
                  disabled={isActivityEmpty}
                  loading={createActivity.isPending}
                >
                  Toevoegen
                </Button>
              </div>
            </div>

            {/* Activity list */}
            {lead.activities.length > 0 ? (
              <div className="space-y-3">
                {[...lead.activities].reverse().map((activity) => (
                  <div key={activity.id} className="flex gap-2.5">
                    <div className="mt-0.5 flex items-center justify-center h-6 w-6 rounded-full bg-gray-100 text-text-secondary shrink-0">
                      {ACTIVITY_ICONS[activity.activity_type]}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 text-xs text-text-secondary">
                        {activity.author_naam && (
                          <span className="font-medium text-text">{activity.author_naam}</span>
                        )}
                        <Badge variant="gray">
                          {LEAD_ACTIVITY_TYPE_LABELS[activity.activity_type]}
                        </Badge>
                        <span>{timeAgo(activity.created_at)}</span>
                      </div>
                      <div className="mt-0.5">
                        <RichTextDisplay content={activity.content} fallback="" />
                      </div>
                      {(activity.uitkomst || activity.vervolgacties) && (
                        <div className="mt-1.5 grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {activity.uitkomst && (
                            <div className="rounded-md bg-emerald-50 border border-emerald-200 px-2 py-1.5 text-xs">
                              <div className="font-semibold text-emerald-800 mb-0.5">
                                Uitkomst
                              </div>
                              <div className="text-text whitespace-pre-wrap">
                                {activity.uitkomst}
                              </div>
                            </div>
                          )}
                          {activity.vervolgacties && (
                            <div className="rounded-md bg-amber-50 border border-amber-200 px-2 py-1.5 text-xs">
                              <div className="font-semibold text-amber-800 mb-0.5">
                                Vervolgacties
                              </div>
                              <div className="text-text whitespace-pre-wrap">
                                {activity.vervolgacties}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-text-secondary">Nog geen activiteiten</p>
            )}
          </DetailSection>
        </div>
      )}
    </Modal>

    {lightboxSrc && (
      <div
        className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60"
        onClick={() => setLightboxSrc(null)}
      >
        <img
          src={lightboxSrc.src}
          alt={lightboxSrc.alt}
          className="max-w-[90vw] max-h-[90vh] rounded-lg shadow-xl"
          onClick={(e) => e.stopPropagation()}
        />
      </div>
    )}
    <ConfirmDialog
      open={showDeleteConfirm}
      onClose={() => setShowDeleteConfirm(false)}
      onConfirm={() => {
        if (lead) deleteLead.mutate(lead.id, { onSuccess: onClose });
        setShowDeleteConfirm(false);
      }}
      title="Lead verwijderen"
      confirmLabel="Verwijderen"
      variant="danger"
    >
      Weet je zeker dat je deze lead wilt verwijderen?
    </ConfirmDialog>
    {showLinkNode && lead && (
      <LinkLeadNodeModal
        leadId={lead.id}
        onClose={() => setShowLinkNode(false)}
      />
    )}
    </>
  );
}
