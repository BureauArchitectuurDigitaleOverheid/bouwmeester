import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import {
  Trash2,
  User,
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
import { RichTextEditor } from '@/components/common/RichTextEditor';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { createPerson } from '@/api/people';
import { Badge } from '@/components/common/Badge';
import { DetailSection } from '@/components/common/DetailSection';
import { DetailModalFooter } from '@/components/common/DetailModalFooter';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { LeadContentLayout } from '@/components/leads/LeadContentLayout';
import {
  useLead,
  useUpdateLead,
  useDeleteLead,
  useMoveLead,
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
import { timeAgo } from '@/utils/dates';
import {
  LeadStage,
  LeadActivityType,
  LEAD_ACTIVITY_TYPE_LABELS,
  LEAD_CONTACT_ROL_LABELS,
} from '@/types';
import type { LeadActivityCreate } from '@/types';

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
  const moveLeadMutation = useMoveLead();
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
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  useEffect(() => {
    if (!lightboxSrc) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLightboxSrc(null);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [lightboxSrc]);

  // Inline save handlers
  const handleSaveTitle = useCallback(async (value: string | null) => {
    if (!lead || !value) return;
    await updateLead.mutateAsync({ id: lead.id, data: { title: value } });
  }, [lead, updateLead]);

  const handleSaveStage = useCallback(async (stage: LeadStage) => {
    if (!lead) return;
    await moveLeadMutation.mutateAsync({ id: lead.id, stage });
  }, [lead, moveLeadMutation]);

  const handleSaveDescription = useCallback(async (value: string | null) => {
    if (!lead) return;
    await updateLead.mutateAsync({ id: lead.id, data: { description: value } });
  }, [lead, updateLead]);

  const handleSaveOrganization = useCallback(async (value: string | null) => {
    if (!lead) return;
    await updateLead.mutateAsync({ id: lead.id, data: { organization: value } });
  }, [lead, updateLead]);

  const handleSaveAssignee = useCallback(async (value: string | null) => {
    if (!lead) return;
    await updateLead.mutateAsync({ id: lead.id, data: { assignee_id: value } });
  }, [lead, updateLead]);

  const handleSaveBroughtBy = useCallback(async (value: string | null) => {
    if (!lead) return;
    await updateLead.mutateAsync({ id: lead.id, data: { brought_by_id: value } });
  }, [lead, updateLead]);

  const handleSaveInitiatief = useCallback(async (value: string | null) => {
    if (!lead) return;
    await updateLead.mutateAsync({ id: lead.id, data: { initiatief_id: value } });
  }, [lead, updateLead]);

  const handleSaveNextAction = useCallback(async (value: string | null) => {
    if (!lead) return;
    await updateLead.mutateAsync({ id: lead.id, data: { next_action: value } });
  }, [lead, updateLead]);

  const handleSaveNextActionDate = useCallback(async (value: string | null) => {
    if (!lead) return;
    await updateLead.mutateAsync({ id: lead.id, data: { next_action_date: value } });
  }, [lead, updateLead]);

  const handleSaveTags = useCallback(async (newTags: string[]) => {
    if (!lead) return;
    const currentNames = (leadTags ?? []).map((lt) => lt.tag.name);
    const toRemove = (leadTags ?? []).filter((lt) => !newTags.includes(lt.tag.name));
    const toAdd = newTags.filter((name) => !currentNames.includes(name));
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
  }, [lead, leadTags, addTagToLead, removeTagFromLead]);

  if (!open) return null;

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

  return (
    <>
    <Modal
      open={open}
      onClose={onClose}
      title={isLoading ? 'Laden...' : 'Lead'}
      size="xl"
      zIndex={zIndex}
      entityLabel="Lead"
      footer={
        <DetailModalFooter
          onClose={onClose}
          actions={
            <Button
              variant="danger"
              size="sm"
              icon={<Trash2 className="h-4 w-4" />}
              onClick={handleDelete}
              disabled={!lead}
            >
              Verwijderen
            </Button>
          }
        />
      }
    >
      {isLoading ? (
        <LoadingSpinner className="py-8" />
      ) : !lead ? (
        <div className="flex items-center justify-center py-8 text-text-secondary text-sm">
          Lead niet gevonden.
        </div>
      ) : (
        <LeadContentLayout
          title={lead.title}
          stage={lead.stage}
          description={lead.description}
          organization={lead.externe_organisatie?.naam ?? lead.organization}
          assigneeId={lead.assignee_id}
          assigneeName={lead.assignee?.naam ?? null}
          broughtById={lead.brought_by_id}
          broughtByName={lead.brought_by?.naam ?? null}
          initiatiefId={lead.initiatief_id}
          initiatiefName={lead.initiatief?.naam ?? null}
          initiatiefKleur={lead.initiatief?.kleur ?? null}
          nextAction={lead.next_action}
          nextActionDate={lead.next_action_date}
          createdAt={lead.created_at}
          tags={(leadTags ?? []).map((lt) => lt.tag.name)}
          onTitleChange={handleSaveTitle}
          onStageChange={handleSaveStage}
          onDescriptionChange={handleSaveDescription}
          onOrganizationChange={handleSaveOrganization}
          onAssigneeChange={handleSaveAssignee}
          onBroughtByChange={handleSaveBroughtBy}
          onInitiatiefChange={handleSaveInitiatief}
          onNextActionChange={handleSaveNextAction}
          onNextActionDateChange={handleSaveNextActionDate}
          onTagsChange={handleSaveTags}
          rightColumnChildren={
            <>
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
            </>
          }
          bottomChildren={
            <>
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
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-text-secondary">Nog geen activiteiten</p>
                )}
              </DetailSection>
            </>
          }
        />
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
    </>
  );
}
