import { useState, useRef, useEffect, useCallback } from 'react';
import { clsx } from 'clsx';
import { ArrowLeft, Pencil, Trash2, Calendar, Link as LinkIcon, Users, X, ExternalLink, UserCircle, Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { PersonCardExpandable } from '@/components/people/PersonCardExpandable';
import { NodeEditForm } from './NodeEditForm';
import { EdgeList } from './EdgeList';
import { TaskView } from '@/components/tasks/TaskView';
import { useNode, useNodeNeighbors, useNodeStakeholders, useDeleteNode, useNodeMotieImport } from '@/hooks/useNodes';
import { useTasks } from '@/hooks/useTasks';
import { useNodeTags, useAddTagToNode, useRemoveTagFromNode, useTags } from '@/hooks/useTags';
import { useReferences } from '@/hooks/useMentions';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { NODE_TYPE_COLORS, STAKEHOLDER_ROL_LABELS } from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';

type TabId = 'overview' | 'connections' | 'stakeholders' | 'tasks' | 'activity';

const tabs: { id: TabId; label: string }[] = [
  { id: 'overview', label: 'Overzicht' },
  { id: 'connections', label: 'Verbindingen' },
  { id: 'stakeholders', label: 'Betrokkenen' },
  { id: 'tasks', label: 'Taken' },
  { id: 'activity', label: 'Activiteit' },
];

interface NodeDetailProps {
  nodeId: string;
}

export function NodeDetail({ nodeId }: NodeDetailProps) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [showEditForm, setShowEditForm] = useState(false);
  const [tagInput, setTagInput] = useState('');
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const [tagHighlightIdx, setTagHighlightIdx] = useState(0);
  const tagContainerRef = useRef<HTMLDivElement>(null);
  const tagInputRef = useRef<HTMLInputElement>(null);
  const tagListRef = useRef<HTMLUListElement>(null);
  const { data: node, isLoading, error } = useNode(nodeId);
  const { data: neighbors } = useNodeNeighbors(nodeId);
  const { data: nodeTasks } = useTasks({ node_id: nodeId });
  const { data: stakeholders } = useNodeStakeholders(nodeId);
  const deleteNode = useDeleteNode();
  const { data: nodeTags } = useNodeTags(nodeId);
  const addTag = useAddTagToNode();
  const removeTag = useRemoveTagFromNode();
  const { nodeLabel, nodeAltLabel } = useVocabulary();
  const { data: motieImport } = useNodeMotieImport(nodeId, node?.node_type);
  const { data: references } = useReferences(nodeId);
  const { openTaskDetail } = useTaskDetail();

  // Tag search: fetch all tags and filter client-side for instant results
  const { data: allTags } = useTags();
  const existingTagIds = new Set(nodeTags?.map((nt) => nt.tag.id) ?? []);
  const debouncedQuery = tagInput.trim().toLowerCase();
  const tagSearchResults = (allTags ?? []).filter(
    (t) => !existingTagIds.has(t.id) && t.name.toLowerCase().includes(debouncedQuery),
  ).slice(0, 10);
  const showCreateTag = debouncedQuery.length > 0 &&
    !tagSearchResults.some((t) => t.name.toLowerCase() === debouncedQuery);
  const tagTotalItems = tagSearchResults.length + (showCreateTag ? 1 : 0);

  // Close tag dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (tagContainerRef.current && !tagContainerRef.current.contains(e.target as Node)) {
        setTagDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  useEffect(() => { setTagHighlightIdx(0); }, [tagInput]);

  useEffect(() => {
    if (tagDropdownOpen && tagListRef.current) {
      const item = tagListRef.current.children[tagHighlightIdx] as HTMLElement | undefined;
      item?.scrollIntoView({ block: 'nearest' });
    }
  }, [tagHighlightIdx, tagDropdownOpen]);

  const handleSelectTag = useCallback((tagId: string) => {
    addTag.mutate({ nodeId, data: { tag_id: tagId } });
    setTagInput('');
    setTagDropdownOpen(false);
  }, [addTag, nodeId]);

  const handleCreateTag = useCallback(() => {
    if (!tagInput.trim()) return;
    addTag.mutate({ nodeId, data: { tag_name: tagInput.trim() } });
    setTagInput('');
    setTagDropdownOpen(false);
  }, [addTag, nodeId, tagInput]);

  const handleTagKeyDown = (e: React.KeyboardEvent) => {
    if (!tagDropdownOpen) {
      if (tagInput.trim() && (e.key === 'ArrowDown' || e.key === 'Enter')) {
        e.preventDefault();
        setTagDropdownOpen(true);
      }
      return;
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setTagHighlightIdx((i) => (i + 1) % tagTotalItems);
        break;
      case 'ArrowUp':
        e.preventDefault();
        setTagHighlightIdx((i) => (i - 1 + tagTotalItems) % tagTotalItems);
        break;
      case 'Enter':
        e.preventDefault();
        if (showCreateTag && tagHighlightIdx === tagSearchResults.length) {
          handleCreateTag();
        } else if (tagSearchResults[tagHighlightIdx]) {
          handleSelectTag(tagSearchResults[tagHighlightIdx].id);
        }
        break;
      case 'Escape':
        e.preventDefault();
        setTagDropdownOpen(false);
        break;
    }
  };

  if (isLoading) {
    return <LoadingSpinner className="py-16" />;
  }

  if (error || !node) {
    return (
      <EmptyState
        title="Node niet gevonden"
        description="De gevraagde node bestaat niet of is verwijderd."
        action={
          <Button variant="secondary" onClick={() => navigate('/corpus')}>
            Terug naar corpus
          </Button>
        }
      />
    );
  }

  const color = NODE_TYPE_COLORS[node.node_type];

  const handleDelete = async () => {
    if (window.confirm('Weet je zeker dat je deze node wilt verwijderen?')) {
      await deleteNode.mutateAsync(node.id);
      navigate('/corpus');
    }
  };

  return (
    <div className="space-y-6">
      {/* Back button */}
      <button
        onClick={() => navigate('/corpus')}
        className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Terug naar corpus
      </button>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Badge variant={color as 'blue'} dot title={nodeAltLabel(node.node_type)}>
              {nodeLabel(node.node_type)}
            </Badge>
            {node.status && <Badge variant="gray">{node.status}</Badge>}
          </div>
          <h1 className="text-2xl font-bold text-text">{node.title}</h1>
          <div className="flex items-center gap-4 mt-2 text-xs text-text-secondary">
            <span className="inline-flex items-center gap-1">
              <Calendar className="h-3.5 w-3.5" />
              Aangemaakt: {new Date(node.created_at).toLocaleDateString('nl-NL')}
            </span>
            <span className="inline-flex items-center gap-1">
              <LinkIcon className="h-3.5 w-3.5" />
              {node.edge_count ?? 0} verbindingen
            </span>
            {motieImport?.document_url && (
              <a
                href={motieImport.document_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-primary-700 hover:text-primary-900 transition-colors"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Bekijk op tweedekamer.nl
              </a>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button variant="secondary" size="sm" icon={<Pencil className="h-4 w-4" />} onClick={() => setShowEditForm(true)}>
            Bewerken
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<Trash2 className="h-4 w-4" />}
            onClick={handleDelete}
            className="text-red-500 hover:bg-red-50 hover:text-red-600"
          >
            Verwijder
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={clsx(
              'px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px',
              activeTab === tab.id
                ? 'border-primary-900 text-primary-900'
                : 'border-transparent text-text-secondary hover:text-text hover:border-border',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Description */}
            <Card>
              <h3 className="text-sm font-medium text-text mb-2">Beschrijving</h3>
              <RichTextDisplay content={node.description} />
            </Card>

            {/* Tags */}
            <Card>
              <h3 className="text-sm font-medium text-text mb-3">Tags</h3>
              <div className="flex flex-wrap gap-1.5 mb-3">
                {nodeTags?.map((nt) => (
                  <span
                    key={nt.id}
                    className="inline-flex items-center gap-1 rounded-full bg-slate-100 text-slate-700 px-2.5 py-0.5 text-xs font-medium"
                  >
                    {nt.tag.name}
                    <button
                      onClick={() => removeTag.mutate({ nodeId, tagId: nt.tag.id })}
                      className="hover:text-red-500 transition-colors ml-0.5"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
                {(!nodeTags || nodeTags.length === 0) && (
                  <span className="text-xs text-text-secondary">Geen tags</span>
                )}
              </div>
              {/* Add tag input with search */}
              <div className="relative" ref={tagContainerRef}>
                <input
                  ref={tagInputRef}
                  type="text"
                  value={tagInput}
                  onChange={(e) => {
                    setTagInput(e.target.value);
                    if (e.target.value.trim()) setTagDropdownOpen(true);
                    else setTagDropdownOpen(false);
                  }}
                  onFocus={() => { if (tagInput.trim()) setTagDropdownOpen(true); }}
                  onKeyDown={handleTagKeyDown}
                  placeholder="Tag zoeken of toevoegen..."
                  className="w-full px-3 py-1.5 text-sm rounded-lg border border-border focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
                />
                {tagDropdownOpen && tagTotalItems > 0 && (
                  <ul
                    ref={tagListRef}
                    className="absolute z-50 mt-1 w-full max-h-48 overflow-auto rounded-xl border border-border bg-white shadow-lg py-1"
                  >
                    {tagSearchResults.map((tag, idx) => (
                      <li
                        key={tag.id}
                        onClick={() => handleSelectTag(tag.id)}
                        onMouseEnter={() => setTagHighlightIdx(idx)}
                        className={clsx(
                          'px-3 py-1.5 text-sm cursor-pointer transition-colors',
                          tagHighlightIdx === idx ? 'bg-primary-50 text-primary-700' : 'text-text hover:bg-gray-50',
                        )}
                      >
                        {tag.name}
                      </li>
                    ))}
                    {showCreateTag && (
                      <li
                        onClick={handleCreateTag}
                        onMouseEnter={() => setTagHighlightIdx(tagSearchResults.length)}
                        className={clsx(
                          'px-3 py-1.5 text-sm cursor-pointer transition-colors flex items-center gap-1.5 border-t border-border',
                          tagHighlightIdx === tagSearchResults.length ? 'bg-primary-50 text-primary-700' : 'text-primary-600 hover:bg-gray-50',
                        )}
                      >
                        <Plus className="h-3.5 w-3.5" />
                        Nieuwe tag: &quot;{tagInput.trim()}&quot;
                      </li>
                    )}
                  </ul>
                )}
              </div>
            </Card>

            {/* Verwijzingen (back-references from mentions) */}
            {references && references.length > 0 && (
              <Card>
                <h3 className="text-sm font-medium text-text mb-3">
                  <LinkIcon className="h-4 w-4 inline mr-1.5 -mt-0.5" />
                  Verwijzingen ({references.length})
                </h3>
                <div className="space-y-1.5">
                  {references.map((ref) => (
                    <button
                      key={`${ref.source_type}-${ref.source_id}`}
                      onClick={() => {
                        if (ref.source_type === 'node') navigate(`/nodes/${ref.source_id}`);
                        else if (ref.source_type === 'task') openTaskDetail(ref.source_id);
                      }}
                      className="flex items-center gap-2 w-full p-2 rounded-lg hover:bg-gray-50 transition-colors text-left"
                    >
                      <Badge variant="gray">
                        {ref.source_type === 'node' ? 'Node' : ref.source_type === 'task' ? 'Taak' : ref.source_type}
                      </Badge>
                      <span className="text-sm text-text truncate">{ref.source_title}</span>
                    </button>
                  ))}
                </div>
              </Card>
            )}

            {/* Metadata */}
            {node.metadata && Object.keys(node.metadata).length > 0 && (
              <Card>
                <h3 className="text-sm font-medium text-text mb-3">Metadata</h3>
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {Object.entries(node.metadata).map(([key, value]) => (
                    <div key={key}>
                      <dt className="text-xs font-medium text-text-secondary capitalize">
                        {key.replace(/_/g, ' ')}
                      </dt>
                      <dd className="text-sm text-text mt-0.5">
                        {String(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </Card>
            )}

            {/* Stakeholders preview */}
            {stakeholders && stakeholders.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-text mb-3">
                  <Users className="h-4 w-4 inline mr-1.5 -mt-0.5" />
                  Betrokkenen ({stakeholders.length})
                </h3>
                <div className="space-y-2">
                  {stakeholders.slice(0, 5).map((s) => (
                    <PersonCardExpandable
                      key={s.id}
                      person={s.person}
                      extraBadge={
                        <Badge variant="slate">
                          {STAKEHOLDER_ROL_LABELS[s.rol] ?? s.rol}
                        </Badge>
                      }
                    />
                  ))}
                  {stakeholders.length > 5 && (
                    <button
                      onClick={() => setActiveTab('stakeholders')}
                      className="text-xs text-primary-700 hover:text-primary-900 transition-colors"
                    >
                      Bekijk alle {stakeholders.length} betrokkenen
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Connected nodes preview */}
            {neighbors && neighbors.length > 0 && (
              <Card>
                <h3 className="text-sm font-medium text-text mb-3">
                  Verbonden nodes ({neighbors.length})
                </h3>
                <div className="space-y-2">
                  {neighbors.slice(0, 5).map((neighbor) => (
                    <button
                      key={neighbor.id}
                      onClick={() => navigate(`/nodes/${neighbor.id}`)}
                      className="flex items-center gap-2 w-full p-2 rounded-lg hover:bg-gray-50 transition-colors text-left"
                    >
                      <Badge variant={NODE_TYPE_COLORS[neighbor.node_type] as 'blue'} dot title={nodeAltLabel(neighbor.node_type)}>
                        {nodeLabel(neighbor.node_type)}
                      </Badge>
                      <span className="text-sm text-text truncate">
                        {neighbor.title}
                      </span>
                    </button>
                  ))}
                  {neighbors.length > 5 && (
                    <button
                      onClick={() => setActiveTab('connections')}
                      className="text-xs text-primary-700 hover:text-primary-900 transition-colors"
                    >
                      Bekijk alle {neighbors.length} verbindingen
                    </button>
                  )}
                </div>
              </Card>
            )}
          </div>
        )}

        {activeTab === 'connections' && (
          <EdgeList nodeId={nodeId} />
        )}

        {activeTab === 'stakeholders' && (
          <div className="space-y-4">
            <h3 className="text-sm font-medium text-text">
              Betrokkenen ({stakeholders?.length ?? 0})
            </h3>
            {stakeholders && stakeholders.length > 0 ? (
              <div className="space-y-2">
                {stakeholders.map((s) => (
                  <PersonCardExpandable
                    key={s.id}
                    person={s.person}
                    extraBadge={
                      <Badge variant="slate">
                        {STAKEHOLDER_ROL_LABELS[s.rol] ?? s.rol}
                      </Badge>
                    }
                  />
                ))}
              </div>
            ) : (
              <EmptyState
                title="Geen betrokkenen"
                description="Er zijn nog geen personen gekoppeld aan deze node."
              />
            )}
          </div>
        )}

        {activeTab === 'tasks' && (
          <TaskView tasks={nodeTasks ?? []} defaultNodeId={nodeId} />
        )}

        {activeTab === 'activity' && (
          <EmptyState
            title="Activiteitentijdlijn"
            description="Hier verschijnt de activiteitsgeschiedenis van deze node."
          />
        )}
      </div>

      {showEditForm && (
        <NodeEditForm
          open={showEditForm}
          onClose={() => setShowEditForm(false)}
          node={node}
        />
      )}
    </div>
  );
}
