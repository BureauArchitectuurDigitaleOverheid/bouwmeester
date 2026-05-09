import { useState, useRef, useEffect } from 'react';
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
  ExternalLink,
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
import { AddLeadContactModal } from './AddLeadContactModal';
import { LeadGitHubLinks } from './LeadGitHubLinks';
import { LeadUpdatesSection } from './LeadUpdatesSection';
import { MattermostChannelsSection } from '@/components/mattermost/MattermostChannelsSection';
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
  useDeleteLeadActivity,
  useRemoveLeadContact,
  useUnlinkLeadNode,
  useUploadLeadAttachment,
  useDeleteLeadAttachment,
  useLeadTags,
  useAddTagToLead,
  useRemoveTagFromLead,
} from '@/hooks/useLeads';
import { useAuth } from '@/contexts/AuthContext';
import { usePeople, useCreatePerson } from '@/hooks/usePeople';
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
  ENGAGEMENT_TYPE_COLORS,
} from '@/types';
import type { LeadUpdate, LeadActivityCreate, EngagementType } from '@/types';

/** Stages where a lead can publicly appear; mirrors the backend filter in
 *  public_initiatief.py — keep in sync. */
const PUBLIC_VISIBLE_STAGES: LeadStage[] = [
  LeadStage.EERSTE_GESPREK,
  LeadStage.INTERNE_CHECK,
  LeadStage.FOLLOW_UP,
  LeadStage.IN_THE_POCKET,
];

interface PublicationStatus {
  /** Will this lead actually appear on the public page right now? */
  visible: boolean;
  /** Human-readable reason when not visible. Null when visible. */
  reason: string | null;
}

function publicationStatus(args: {
  publicVisible: boolean;
  publicTitle: string | null;
  stage: string;
}): PublicationStatus {
  if (!args.publicVisible) {
    return { visible: false, reason: 'Toggle "Publiek tonen" staat uit.' };
  }
  if (!args.publicTitle?.trim()) {
    return { visible: false, reason: 'Publieke titel is leeg.' };
  }
  // Heuristiek-fallback: voor de detail-panel-hint gebruiken we de
  // 7-default whitelist. De backend doet de echte check op
  // LeadColumn.is_public_visible per initiatief; deze UI-hint hoeft
  // alleen "ongeveer juist" te zijn voor default-stages.
  if (!PUBLIC_VISIBLE_STAGES.includes(args.stage as LeadStage)) {
    const label = LEAD_STAGE_LABELS[args.stage] ?? args.stage;
    return {
      visible: false,
      reason: `Lead in stage "${label}" — alleen actieve stages worden publiek.`,
    };
  }
  return { visible: true, reason: null };
}

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
  const createPerson = useCreatePerson();

  const updateLead = useUpdateLead();
  const deleteLead = useDeleteLead();
  const createActivity = useCreateLeadActivity();
  const deleteActivity = useDeleteLeadActivity();
  const { person } = useAuth();
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
  const [editStage, setEditStage] = useState<string>(LeadStage.VERKENNEN);
  const [editAssignee, setEditAssignee] = useState('');
  const [editNextAction, setEditNextAction] = useState('');
  const [editNextActionDate, setEditNextActionDate] = useState('');
  const [editInitiatiefId, setEditInitiatiefId] = useState('');
  const [editTags, setEditTags] = useState('');
  const [editEngagementType, setEditEngagementType] = useState<EngagementType | ''>('');
  const [editScoreStrategisch, setEditScoreStrategisch] = useState<number | ''>('');
  const [editScorePolitiek, setEditScorePolitiek] = useState<number | ''>('');
  const [editScorePositie, setEditScorePositie] = useState<number | ''>('');
  const [editPublicVisible, setEditPublicVisible] = useState(false);
  const [editPublicTitle, setEditPublicTitle] = useState('');
  const [editPublicSummary, setEditPublicSummary] = useState('');

  // Activity form
  const [activityContent, setActivityContent] = useState('');
  const [activityType, setActivityType] = useState<LeadActivityType>(LeadActivityType.NOTE);
  const [activityUitkomst, setActivityUitkomst] = useState('');
  const [activityVervolgacties, setActivityVervolgacties] = useState('');

  // Contact add form
  const [showAddContact, setShowAddContact] = useState(false);

  // Node link modal
  const [showLinkNode, setShowLinkNode] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [lightboxSrc, setLightboxSrc] = useState<{ src: string; alt: string } | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [activityToDelete, setActivityToDelete] = useState<string | null>(null);

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
    setEditPublicVisible(lead.public_visible);
    setEditPublicTitle(lead.public_title ?? '');
    setEditPublicSummary(lead.public_summary ?? '');
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
      public_visible: editPublicVisible,
      public_title: editPublicTitle.trim() || null,
      public_summary: editPublicSummary.trim() || null,
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
                  const result = await createPerson.mutateAsync({ naam: name, force: true });
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
          {(() => {
            const linkedInit = initiatieven?.find((i) => i.id === editInitiatiefId);
            if (!linkedInit?.public_page_enabled) return null;
            const status = publicationStatus({
              publicVisible: editPublicVisible,
              publicTitle: editPublicTitle,
              stage: editStage,
            });
            return (
              <div className="space-y-3 rounded-lg border border-emerald-200 bg-emerald-50/40 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs text-emerald-900 uppercase tracking-wider font-semibold">
                    Publicatie op /c/{linkedInit.slug}
                  </div>
                  <label className="flex items-center gap-2 text-sm text-emerald-900 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editPublicVisible}
                      onChange={(e) => setEditPublicVisible(e.target.checked)}
                      className="h-4 w-4 rounded border-emerald-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    Publiek tonen
                  </label>
                </div>
                {editPublicVisible && !status.visible && (
                  <div className="rounded-md bg-amber-50 border border-amber-200 px-2 py-1.5 text-xs text-amber-900">
                    <strong>Nog niet zichtbaar:</strong> {status.reason}
                  </div>
                )}
                <p className="text-xs text-emerald-800/80">
                  Schrijf een externe titel en samenvatting. Alleen die tekst
                  verschijnt op de publieke pagina, nooit het interne titel- of
                  beschrijvingsveld.
                </p>
                <div>
                  <label className="block text-sm font-medium text-text mb-1">
                    Publieke titel
                  </label>
                  <input
                    type="text"
                    value={editPublicTitle}
                    onChange={(e) => setEditPublicTitle(e.target.value)}
                    placeholder="Bijv. 'Pilot bij Gemeente Utrecht'"
                    className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-white focus:outline-none focus:border-emerald-400"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-text mb-1">
                    Publieke samenvatting
                  </label>
                  <textarea
                    value={editPublicSummary}
                    onChange={(e) => setEditPublicSummary(e.target.value)}
                    placeholder="Korte tekst voor buitenstaanders. Geen interne details, geen namen van conflicten."
                    rows={3}
                    className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-white focus:outline-none focus:border-emerald-400"
                  />
                </div>
                <p className="text-xs text-text-secondary">
                  Verschijnt alleen als de stage actief is (eerste gesprek, interne
                  check, follow-up of in the pocket) én "Publiek tonen" aan staat én
                  de titel ingevuld is.
                </p>
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
                value: lead.organisatie_eenheid?.naam ?? lead.organization ?? 'Onbekend',
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
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${ENGAGEMENT_TYPE_COLORS[lead.engagement_type]}`}
                      >
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

          {/* Publicatie-status */}
          {(() => {
            const linkedInit = initiatieven?.find(
              (i) => i.id === lead.initiatief_id,
            );
            if (!linkedInit?.public_page_enabled) return null;
            if (!lead.public_visible && !lead.public_title) return null;
            const status = publicationStatus({
              publicVisible: lead.public_visible,
              publicTitle: lead.public_title,
              stage: lead.stage,
            });
            return (
              <DetailSection title="Publicatie">
                <div className="space-y-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    {status.visible ? (
                      <a
                        href={`/c/${linkedInit.slug}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 group"
                      >
                        <Badge variant="green">
                          <span className="inline-flex items-center gap-1 group-hover:underline">
                            Zichtbaar op /c/{linkedInit.slug}
                            <ExternalLink className="h-3 w-3" />
                          </span>
                        </Badge>
                      </a>
                    ) : (
                      <Badge variant="gray">Niet zichtbaar</Badge>
                    )}
                  </div>
                  {!status.visible && status.reason && (
                    <p className="text-xs text-text-secondary">
                      {status.reason}
                    </p>
                  )}
                  {lead.public_title && (
                    <div className="text-sm">
                      <span className="text-text-secondary">Publieke titel: </span>
                      <span className="text-text font-medium">
                        {lead.public_title}
                      </span>
                    </div>
                  )}
                  {lead.public_summary && (
                    <div className="text-sm text-text-secondary whitespace-pre-wrap">
                      {lead.public_summary}
                    </div>
                  )}
                </div>
              </DetailSection>
            );
          })()}

          <LeadUpdatesSection leadId={lead.id} />

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
                      {att.soort === 'link' ? (
                        <ExternalLink className="h-3.5 w-3.5 text-text-secondary shrink-0" />
                      ) : (
                        <Paperclip className="h-3.5 w-3.5 text-text-secondary shrink-0" />
                      )}
                      {att.soort === 'link' && att.url ? (
                        <a
                          href={att.url}
                          target="_blank"
                          rel="noreferrer"
                          className="flex-1 truncate text-primary-700 hover:underline"
                          title={att.url}
                        >
                          {att.bestandsnaam ?? att.url}
                        </a>
                      ) : (
                        <span className="flex-1 truncate text-text">{att.bestandsnaam ?? '(naamloos)'}</span>
                      )}
                      {att.source === 'mattermost' && (
                        <span className="text-[10px] uppercase tracking-wider text-text-secondary px-1.5 py-0.5 rounded bg-gray-100">
                          via mm
                        </span>
                      )}
                      {att.soort === 'file' && !att.bestand_beschikbaar ? (
                        <span className="text-xs text-red-500">Bestand niet beschikbaar</span>
                      ) : att.soort === 'file' ? (
                        <>
                          <span className="text-xs text-text-secondary">{Math.round((att.bestandsgrootte ?? 0) / 1024)} KB</span>
                          <a
                            href={getLeadAttachmentDownloadUrl(lead.id, att.id)}
                            className="p-1 text-text-secondary hover:text-primary-600 transition-colors"
                            title="Downloaden"
                          >
                            <Download className="h-3.5 w-3.5" />
                          </a>
                        </>
                      ) : null}
                      <button
                        onClick={() => deleteAttachment.mutate({ leadId: lead.id, attachmentId: att.id })}
                        className="p-1 text-text-secondary hover:text-red-500 transition-colors"
                        title="Verwijderen"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    {att.soort === 'file' && att.bestand_beschikbaar && att.content_type?.startsWith('image/') && (
                      <button
                        onClick={() => setLightboxSrc({
                          src: getLeadAttachmentDownloadUrl(lead.id, att.id),
                          alt: att.bestandsnaam ?? 'bijlage',
                        })}
                        className="relative group mt-2 ml-2 block"
                      >
                        <img
                          src={getLeadAttachmentDownloadUrl(lead.id, att.id)}
                          alt={att.bestandsnaam ?? 'bijlage'}
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

          <LeadGitHubLinks leadId={lead.id} links={lead.github_links ?? []} />

          {/* Externe contactpersonen */}
          <DetailSection
            title="Externe contactpersonen"
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
                    {contact.person_expertise && (
                      <Badge variant="indigo">{contact.person_expertise}</Badge>
                    )}
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
              <p className="text-sm text-text-secondary">Geen externe contactpersonen</p>
            )}

            <AddLeadContactModal
              leadId={showAddContact ? lead.id : null}
              onClose={() => setShowAddContact(false)}
            />
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
                {[...lead.activities].reverse().map((activity) => {
                  const canDelete =
                    !!person &&
                    (person.is_admin ||
                      (person.id !== null && activity.author_id === person.id));
                  return (
                  <div key={activity.id} className="group flex gap-2.5">
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
                        {activity.metadata_?.source === 'mattermost' && (
                          (() => {
                            const permalink = activity.metadata_?.mm_permalink;
                            const badge = (
                              <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">
                                via Mattermost
                              </span>
                            );
                            return typeof permalink === 'string' ? (
                              <a
                                href={permalink}
                                target="_blank"
                                rel="noreferrer"
                                title="Open in Mattermost"
                              >
                                {badge}
                              </a>
                            ) : badge;
                          })()
                        )}
                        <span>{timeAgo(activity.created_at)}</span>
                        {canDelete && (
                          <button
                            type="button"
                            onClick={() => setActivityToDelete(activity.id)}
                            className="ml-auto text-text-secondary sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100 hover:text-red-600 focus:outline-none transition-opacity"
                            aria-label="Activiteit verwijderen"
                            title="Verwijderen"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
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
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-text-secondary">Nog geen activiteiten</p>
            )}
          </DetailSection>

          {/* Mattermost-kanalen */}
          <DetailSection title="Mattermost" separated>
            <MattermostChannelsSection
              scope={{ type: 'lead', id: lead.id }}
              parentZIndex={zIndex}
            />
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
    <ConfirmDialog
      open={activityToDelete !== null}
      onClose={() => setActivityToDelete(null)}
      onConfirm={() => {
        if (lead && activityToDelete) {
          deleteActivity.mutate({ leadId: lead.id, activityId: activityToDelete });
        }
        setActivityToDelete(null);
      }}
      title="Activiteit verwijderen"
      confirmLabel="Verwijderen"
      variant="danger"
    >
      Weet je zeker dat je deze activiteit wilt verwijderen? Deze actie kan niet ongedaan worden gemaakt.
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
