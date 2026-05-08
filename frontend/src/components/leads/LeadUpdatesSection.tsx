import { useState } from 'react';
import { Megaphone, Mail, Sparkles, Trash2, Pencil, Globe, EyeOff, Upload } from 'lucide-react';

import { Button } from '@/components/common/Button';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { DetailSection } from '@/components/common/DetailSection';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import { getLeadUpdateEmlUrl } from '@/api/leadUpdates';
import {
  useCreateLeadUpdate,
  useDeleteLeadUpdate,
  useEditLeadUpdate,
  useLeadUpdates,
  useParseLeadUpdate,
  usePublishLeadUpdate,
  useUnpublishLeadUpdate,
} from '@/hooks/useLeadUpdates';
import { formatDateLong } from '@/utils/dates';
import type { LeadUpdatePost } from '@/types';

interface Draft {
  titel: string;
  body_internal: string;
  body_public: string;
  mail_subject: string;
  mail_to: string[];
  mail_cc: string[];
  source_raw_text: string;
}

const emptyDraft = (): Draft => ({
  titel: '',
  body_internal: '',
  body_public: '',
  mail_subject: '',
  mail_to: [],
  mail_cc: [],
  source_raw_text: '',
});

export function LeadUpdatesSection({ leadId }: { leadId: string }) {
  const { data: posts = [] } = useLeadUpdates(leadId);
  const createMutation = useCreateLeadUpdate();
  const editMutation = useEditLeadUpdate();
  const publishMutation = usePublishLeadUpdate();
  const unpublishMutation = useUnpublishLeadUpdate();
  const deleteMutation = useDeleteLeadUpdate();
  const parseMutation = useParseLeadUpdate();

  const [composing, setComposing] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft());
  const [rawText, setRawText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const concepts = posts.filter((p) => !p.published_at);
  const published = posts.filter((p) => p.published_at);

  const startCompose = () => {
    setDraft(emptyDraft());
    setRawText('');
    setFiles([]);
    setEditingId(null);
    setComposing(true);
    setError(null);
  };

  const startEdit = (post: LeadUpdatePost) => {
    setDraft({
      titel: post.titel,
      body_internal: post.body_internal ?? '',
      body_public: post.body_public ?? '',
      mail_subject: post.mail_subject ?? '',
      mail_to: post.mail_to ?? [],
      mail_cc: post.mail_cc ?? [],
      source_raw_text: '',
    });
    setRawText('');
    setFiles([]);
    setEditingId(post.id);
    setComposing(true);
    setError(null);
  };

  const cancel = () => {
    setComposing(false);
    setEditingId(null);
    setError(null);
  };

  const runExtract = async (useLeadHistory: boolean) => {
    setError(null);
    try {
      const result = await parseMutation.mutateAsync({
        leadId,
        rawText: rawText || undefined,
        useLeadHistory,
        files: files.length ? files : undefined,
      });
      setDraft((d) => ({
        ...d,
        titel: result.titel ?? d.titel,
        body_internal: result.body_internal ?? d.body_internal,
        body_public: result.body_public ?? d.body_public,
        mail_subject: result.mail_subject ?? d.mail_subject,
        mail_to: d.mail_to.length ? d.mail_to : result.suggested_to ?? [],
        mail_cc: d.mail_cc.length ? d.mail_cc : result.suggested_cc ?? [],
        source_raw_text: rawText,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Onbekende fout bij AI-extract.');
    }
  };

  const handleSave = async (publish: boolean) => {
    if (!draft.titel.trim()) return;
    const payload = {
      titel: draft.titel,
      body_internal: draft.body_internal || null,
      body_public: draft.body_public || null,
      mail_subject: draft.mail_subject || null,
      mail_to: draft.mail_to.length ? draft.mail_to : null,
      mail_cc: draft.mail_cc.length ? draft.mail_cc : null,
    };
    if (editingId) {
      await editMutation.mutateAsync({ leadId, postId: editingId, data: payload });
      if (publish) {
        await publishMutation.mutateAsync({ leadId, postId: editingId });
      }
    } else {
      await createMutation.mutateAsync({
        leadId,
        data: {
          ...payload,
          source_raw_text: draft.source_raw_text || null,
          publish,
        },
      });
    }
    cancel();
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    await deleteMutation.mutateAsync({ leadId, postId: confirmDelete });
    setConfirmDelete(null);
  };

  return (
    <DetailSection title="Updates" icon={<Megaphone className="h-3.5 w-3.5" />}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-text-secondary">
          {posts.length === 0 ? 'Nog geen updates' : `${posts.length} totaal`}
        </span>
        {!composing && (
          <Button variant="secondary" size="sm" onClick={startCompose}>
            Nieuwe update
          </Button>
        )}
      </div>

      {composing && (
        <div className="rounded-xl border border-border p-3 mb-3 space-y-3">
          {!editingId && (
            <div className="space-y-2 rounded-lg bg-surface-subtle p-2">
              <label className="text-xs font-medium text-text-secondary">
                Ruwe invoer (plak tekst, of upload bestand)
              </label>
              <textarea
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                rows={4}
                placeholder="Plak hier een mailfragment, gespreksnotitie, of korte beschrijving..."
                className="w-full text-sm rounded-lg border border-border px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <div className="flex items-center gap-2 flex-wrap">
                <label className="inline-flex items-center gap-1 text-xs cursor-pointer text-text-secondary hover:text-text">
                  <Upload className="h-3.5 w-3.5" />
                  Bestand toevoegen
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.docx,.doc,.odt,.txt,image/*"
                    className="hidden"
                    onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
                  />
                </label>
                {files.length > 0 && (
                  <span className="text-xs text-text-secondary">
                    {files.map((f) => f.name).join(', ')}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => runExtract(false)}
                  disabled={
                    parseMutation.isPending ||
                    (!rawText.trim() && files.length === 0)
                  }
                >
                  <Sparkles className="h-3.5 w-3.5 mr-1" />
                  AI: extract uit invoer
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => runExtract(true)}
                  disabled={parseMutation.isPending}
                  title="Genereer een update op basis van de lead-historie (notes, contacten, recente activity)"
                >
                  <Sparkles className="h-3.5 w-3.5 mr-1" />
                  AI: uit lead-historie
                </Button>
                {parseMutation.isPending && (
                  <span className="text-xs text-text-secondary">Bezig...</span>
                )}
              </div>
              {error && <p className="text-xs text-red-600">{error}</p>}
            </div>
          )}

          <input
            type="text"
            value={draft.titel}
            onChange={(e) => setDraft({ ...draft, titel: e.target.value })}
            placeholder="Titel"
            className="w-full text-sm rounded-lg border border-border px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary"
          />

          <RichTextFormField
            label="Interne mailtekst (voor team)"
            value={draft.body_internal}
            onChange={(v) => setDraft({ ...draft, body_internal: v })}
            rows={6}
          />

          <RichTextFormField
            label="Publieke samenvatting (community-pagina)"
            value={draft.body_public}
            onChange={(v) => setDraft({ ...draft, body_public: v })}
            rows={3}
          />

          <div className="grid grid-cols-1 gap-2">
            <div>
              <label className="text-xs font-medium text-text-secondary">
                Mail-onderwerp
              </label>
              <input
                type="text"
                value={draft.mail_subject}
                onChange={(e) => setDraft({ ...draft, mail_subject: e.target.value })}
                className="w-full text-sm rounded-lg border border-border px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <EmailListInput
              label="To"
              value={draft.mail_to}
              onChange={(v) => setDraft({ ...draft, mail_to: v })}
            />
            <EmailListInput
              label="Cc"
              value={draft.mail_cc}
              onChange={(v) => setDraft({ ...draft, mail_cc: v })}
            />
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={cancel}>
              Annuleren
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleSave(false)}
              disabled={!draft.titel.trim()}
            >
              Opslaan als concept
            </Button>
            <Button
              size="sm"
              onClick={() => handleSave(true)}
              disabled={!draft.titel.trim()}
            >
              {editingId ? 'Opslaan + publiceren' : 'Direct publiceren'}
            </Button>
          </div>
        </div>
      )}

      {concepts.length > 0 && (
        <div className="mb-3">
          <div className="text-xs text-text-secondary mb-1">Concepten</div>
          <ul className="divide-y divide-border rounded-xl border border-border">
            {concepts.map((post) => (
              <UpdateRow
                key={post.id}
                leadId={leadId}
                post={post}
                onEdit={() => startEdit(post)}
                onPublish={() =>
                  publishMutation.mutate({ leadId, postId: post.id })
                }
                onUnpublish={() =>
                  unpublishMutation.mutate({ leadId, postId: post.id })
                }
                onDelete={() => setConfirmDelete(post.id)}
              />
            ))}
          </ul>
        </div>
      )}

      {published.length > 0 && (
        <div>
          <div className="text-xs text-text-secondary mb-1">Gepubliceerd</div>
          <ul className="divide-y divide-border rounded-xl border border-border">
            {published.map((post) => (
              <UpdateRow
                key={post.id}
                leadId={leadId}
                post={post}
                onEdit={() => startEdit(post)}
                onPublish={() =>
                  publishMutation.mutate({ leadId, postId: post.id })
                }
                onUnpublish={() =>
                  unpublishMutation.mutate({ leadId, postId: post.id })
                }
                onDelete={() => setConfirmDelete(post.id)}
              />
            ))}
          </ul>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        title="Update verwijderen?"
        message="Weet je zeker dat je deze update wilt verwijderen?"
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(null)}
      />
    </DetailSection>
  );
}

function UpdateRow({
  leadId,
  post,
  onEdit,
  onPublish,
  onUnpublish,
  onDelete,
}: {
  leadId: string;
  post: LeadUpdatePost;
  onEdit: () => void;
  onPublish: () => void;
  onUnpublish: () => void;
  onDelete: () => void;
}) {
  const isPublished = !!post.published_at;
  return (
    <li className="p-2 flex items-start gap-3">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{post.titel}</div>
        <div className="text-xs text-text-secondary">
          {isPublished
            ? `Gepubliceerd ${formatDateLong(post.published_at!)}${post.published_by_naam ? ` · ${post.published_by_naam}` : ''}`
            : `Concept · ${formatDateLong(post.created_at)}`}
        </div>
        {post.body_public && (
          <div className="text-xs text-text-secondary mt-1 line-clamp-2 whitespace-pre-wrap">
            {post.body_public}
          </div>
        )}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <a
          href={getLeadUpdateEmlUrl(leadId, post.id)}
          download
          className="inline-flex items-center text-xs text-text-secondary hover:text-text px-1.5 py-1 rounded hover:bg-surface-subtle"
          title="Download .eml — opent als nieuw concept in Outlook (Windows) met onderwerp en ontvangers ingevuld"
        >
          <Mail className="h-3.5 w-3.5 mr-1" />
          Outlook
        </a>
        <button
          onClick={onEdit}
          className="text-text-secondary hover:text-text p-1 rounded hover:bg-surface-subtle"
          title="Bewerken"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        {isPublished ? (
          <button
            onClick={onUnpublish}
            className="text-text-secondary hover:text-text p-1 rounded hover:bg-surface-subtle"
            title="Depubliceren"
          >
            <EyeOff className="h-3.5 w-3.5" />
          </button>
        ) : (
          <button
            onClick={onPublish}
            className="text-text-secondary hover:text-text p-1 rounded hover:bg-surface-subtle"
            title="Publiceren"
          >
            <Globe className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          onClick={onDelete}
          className="text-text-secondary hover:text-red-600 p-1 rounded hover:bg-surface-subtle"
          title="Verwijderen"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </li>
  );
}

function EmailListInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const [text, setText] = useState(value.join(', '));
  return (
    <div>
      <label className="text-xs font-medium text-text-secondary">{label}</label>
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          const list = text
            .split(/[,;\s]+/)
            .map((s) => s.trim())
            .filter(Boolean);
          onChange(list);
          setText(list.join(', '));
        }}
        placeholder="email@example.org, ..."
        className="w-full text-sm rounded-lg border border-border px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary"
      />
    </div>
  );
}
