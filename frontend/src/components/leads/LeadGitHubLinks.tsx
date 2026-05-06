import { useState } from 'react';
import {
  GitBranch,
  GitPullRequest,
  CircleDot,
  Github,
  Play,
  ExternalLink,
  Pencil,
  Trash2,
  Check,
  X,
  Plus,
} from 'lucide-react';
import { Button } from '@/components/common/Button';
import { DetailSection } from '@/components/common/DetailSection';
import { ApiError } from '@/api/client';
import {
  useAddLeadGitHubLink,
  useUpdateLeadGitHubLink,
  useDeleteLeadGitHubLink,
} from '@/hooks/useLeads';
import type { LeadGitHubLink, GitHubLinkType } from '@/types';

interface Props {
  leadId: string;
  links: LeadGitHubLink[];
}

const TYPE_ICONS: Record<GitHubLinkType, React.ReactNode> = {
  branch: <GitBranch className="h-3.5 w-3.5 text-text-secondary shrink-0" />,
  pull_request: <GitPullRequest className="h-3.5 w-3.5 text-text-secondary shrink-0" />,
  issue: <CircleDot className="h-3.5 w-3.5 text-text-secondary shrink-0" />,
  repo: <Github className="h-3.5 w-3.5 text-text-secondary shrink-0" />,
  workflow_run: <Play className="h-3.5 w-3.5 text-text-secondary shrink-0" />,
  other: <ExternalLink className="h-3.5 w-3.5 text-text-secondary shrink-0" />,
};

const TYPE_LABELS: Record<GitHubLinkType, string> = {
  branch: 'branch',
  pull_request: 'PR',
  issue: 'issue',
  repo: 'repo',
  workflow_run: 'run',
  other: 'link',
};

function shortRef(link: LeadGitHubLink): string {
  if (link.link_type === 'pull_request' || link.link_type === 'issue') {
    return `#${link.ref ?? '?'}`;
  }
  if (link.link_type === 'workflow_run') {
    return `run ${link.ref ?? '?'}`;
  }
  if (link.link_type === 'branch') {
    return link.ref ?? '?';
  }
  return '';
}

export function LeadGitHubLinks({ leadId, links }: Props) {
  const [showForm, setShowForm] = useState(false);
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  const addLink = useAddLeadGitHubLink();
  const updateLink = useUpdateLeadGitHubLink();
  const deleteLink = useDeleteLeadGitHubLink();

  const submit = async () => {
    setError(null);
    const trimmed = url.trim();
    if (!trimmed) {
      setError('Plak een GitHub-URL.');
      return;
    }
    try {
      await addLink.mutateAsync({
        leadId,
        url: trimmed,
        title: title.trim() || null,
      });
      setUrl('');
      setTitle('');
      setShowForm(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        setError('Geen geldige GitHub-URL.');
      } else if (e instanceof ApiError && e.status === 409) {
        setError('Deze link is al gekoppeld.');
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError('Kon link niet toevoegen.');
      }
    }
  };

  const startEdit = (link: LeadGitHubLink) => {
    setEditingId(link.id);
    setEditingTitle(link.title ?? '');
  };

  const saveEdit = async (link: LeadGitHubLink) => {
    await updateLink.mutateAsync({
      leadId,
      linkId: link.id,
      title: editingTitle.trim() || null,
    });
    setEditingId(null);
  };

  return (
    <DetailSection
      title="GitHub-werk"
      icon={<Github className="h-3.5 w-3.5" />}
      count={links.length}
      separated
      action={
        <Button
          variant="ghost"
          size="sm"
          icon={<Plus className="h-3.5 w-3.5" />}
          onClick={() => setShowForm((v) => !v)}
        >
          Link toevoegen
        </Button>
      }
    >
      {showForm && (
        <div className="mb-3 space-y-2 rounded-lg border border-border bg-gray-50 p-3">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo/pull/123"
            className="w-full rounded-md border border-border px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none"
            autoFocus
          />
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Titel (optioneel)"
            className="w-full rounded-md border border-border px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none"
          />
          {error && <p className="text-xs text-red-500">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setShowForm(false);
                setUrl('');
                setTitle('');
                setError(null);
              }}
            >
              Annuleren
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={submit}
              disabled={addLink.isPending}
            >
              Toevoegen
            </Button>
          </div>
        </div>
      )}

      {links.length > 0 ? (
        <div className="space-y-1">
          {links.map((link) => {
            const ref = shortRef(link);
            const display =
              link.title ??
              (ref ? `${link.owner}/${link.repo} ${ref}` : `${link.owner}/${link.repo}`);
            return (
              <div
                key={link.id}
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-gray-50"
              >
                {TYPE_ICONS[link.link_type]}
                {editingId === link.id ? (
                  <>
                    <input
                      type="text"
                      value={editingTitle}
                      onChange={(e) => setEditingTitle(e.target.value)}
                      className="flex-1 rounded-md border border-border px-1.5 py-0.5 text-sm"
                      autoFocus
                    />
                    <button
                      onClick={() => saveEdit(link)}
                      className="p-1 text-text-secondary hover:text-green-600"
                      title="Opslaan"
                    >
                      <Check className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="p-1 text-text-secondary hover:text-red-500"
                      title="Annuleren"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </>
                ) : (
                  <>
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex-1 truncate text-primary-700 hover:underline"
                      title={link.url}
                    >
                      {display}
                    </a>
                    <span className="text-[10px] uppercase tracking-wider text-text-secondary px-1.5 py-0.5 rounded bg-gray-100">
                      {TYPE_LABELS[link.link_type]}
                    </span>
                    <button
                      onClick={() => startEdit(link)}
                      className="p-1 text-text-secondary hover:text-primary-600"
                      title="Titel bewerken"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() =>
                        deleteLink.mutate({ leadId, linkId: link.id })
                      }
                      className="p-1 text-text-secondary hover:text-red-500"
                      title="Verwijderen"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        !showForm && (
          <p className="text-sm text-text-secondary">
            Nog geen GitHub-werk gekoppeld. Plak een URL van een branch, PR of
            issue.
          </p>
        )
      )}
    </DetailSection>
  );
}
