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
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
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
  useLinkLeadNode,
  useUnlinkLeadNode,
  useUploadLeadAttachment,
  useDeleteLeadAttachment,
  useLeadTags,
  useAddTagToLead,
  useRemoveTagFromLead,
} from '@/hooks/useLeads';
import { usePeople } from '@/hooks/usePeople';
import { useNodes } from '@/hooks/useNodes';
import { getLeadAttachmentDownloadUrl } from '@/api/leads';
import { isOverdue, formatDateLong, timeAgo } from '@/utils/dates';
import {
  LeadStage,
  LEAD_STAGE_LABELS,
  LEAD_STAGE_COLORS,
  LEAD_STAGE_ORDER,
  LeadActivityType,
  LEAD_ACTIVITY_TYPE_LABELS,
} from '@/types';
import type { LeadUpdate, LeadActivityCreate } from '@/types';

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
};

export function LeadDetailPanel({ leadId, open, onClose, zIndex }: LeadDetailPanelProps) {
  const { data: lead, isLoading } = useLead(leadId);
  const { data: people } = usePeople();
  const { data: nodes } = useNodes();

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
  const linkNode = useLinkLeadNode();
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
  const [editTags, setEditTags] = useState('');

  // Activity form
  const [activityContent, setActivityContent] = useState('');
  const [activityType, setActivityType] = useState<LeadActivityType>(LeadActivityType.NOTE);

  // Contact add form
  const [showAddContact, setShowAddContact] = useState(false);
  const [contactPersonId, setContactPersonId] = useState('');
  const [contactRol, setContactRol] = useState('contactpersoon');

  // Node link form
  const [showLinkNode, setShowLinkNode] = useState(false);
  const [linkNodeId, setLinkNodeId] = useState('');

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [lightboxSrc, setLightboxSrc] = useState<{ src: string; alt: string } | null>(null);

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
    setEditTags((leadTags ?? []).map((lt) => lt.tag.name).join(', '));
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
    if (!lead || !confirm('Weet je zeker dat je deze lead wilt verwijderen?')) return;
    deleteLead.mutate(lead.id, { onSuccess: onClose });
  };

  const handleAddActivity = () => {
    if (!lead || !activityContent.trim()) return;
    const data: LeadActivityCreate = {
      content: activityContent.trim(),
      activity_type: activityType,
    };
    createActivity.mutate(
      { leadId: lead.id, data },
      {
        onSuccess: () => {
          setActivityContent('');
          setActivityType(LeadActivityType.NOTE);
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

  const handleLinkNode = () => {
    if (!lead || !linkNodeId) return;
    linkNode.mutate(
      { leadId: lead.id, nodeId: linkNodeId },
      {
        onSuccess: () => {
          setShowLinkNode(false);
          setLinkNodeId('');
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
                  const result = await createPerson({ naam: name });
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
          <div>
            <label className="block text-sm font-medium text-text mb-1">Beschrijving</label>
            <textarea
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400 min-h-[80px] resize-y"
              rows={3}
            />
          </div>
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
              <p className="text-sm text-text whitespace-pre-wrap">{lead.description}</p>
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
                label: 'Eenheid',
                value: lead.organisatie_eenheid?.naam ?? '-',
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
                    <div className="flex items-center gap-2 text-sm rounded-lg px-2 py-1.5 hover:bg-gray-50">
                      <Paperclip className="h-3.5 w-3.5 text-text-secondary shrink-0" />
                      <span className="flex-1 truncate text-text">{att.bestandsnaam}</span>
                      <span className="text-xs text-text-secondary">{Math.round(att.bestandsgrootte / 1024)} KB</span>
                      <a
                        href={getLeadAttachmentDownloadUrl(lead.id, att.id)}
                        className="p-1 text-text-secondary hover:text-primary-600 transition-colors"
                        title="Downloaden"
                      >
                        <Download className="h-3.5 w-3.5" />
                      </a>
                      <button
                        onClick={() => deleteAttachment.mutate({ leadId: lead.id, attachmentId: att.id })}
                        className="p-1 text-text-secondary hover:text-red-500 transition-colors"
                        title="Verwijderen"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    {att.content_type?.startsWith('image/') && (
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
                    <Badge variant="gray">{contact.rol}</Badge>
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
                        const newPerson = await createPerson({ naam: name });
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

            {showLinkNode && (
              <div className="flex items-center gap-2 mt-2">
                <div className="flex-1">
                  <CreatableSelect
                    value={linkNodeId}
                    onChange={setLinkNodeId}
                    options={nodes?.map((n) => ({
                      value: n.id,
                      label: n.title,
                      description: n.node_type?.replace(/_/g, ' ') ?? undefined,
                    })) ?? []}
                    placeholder="Zoek een node..."
                  />
                </div>
                <Button size="sm" onClick={handleLinkNode} disabled={!linkNodeId}>
                  Koppelen
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setShowLinkNode(false)}>
                  Annuleren
                </Button>
              </div>
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
              <textarea
                value={activityContent}
                onChange={(e) => setActivityContent(e.target.value)}
                placeholder="Voeg een notitie of activiteit toe..."
                className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:border-primary-400 min-h-[60px] resize-y"
                rows={2}
              />
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
                  disabled={!activityContent.trim()}
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
                      <p className="text-sm text-text mt-0.5 whitespace-pre-wrap">{activity.content}</p>
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
    </>
  );
}
