import { useState, useRef, useEffect, useCallback } from 'react';
import { clsx } from 'clsx';
import { ArrowLeft, Pencil, Trash2, Calendar, Link as LinkIcon, Users, X, ExternalLink, Plus, Download, Upload, FileText } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { PersonCardExpandable } from '@/components/people/PersonCardExpandable';
import { PersonQuickCreateForm } from '@/components/people/PersonQuickCreateForm';
import { NodeEditForm } from './NodeEditForm';
import { EdgeList } from './EdgeList';
import { TaskView } from '@/components/tasks/TaskView';
import { useNode, useNodeNeighbors, useNodeStakeholders, useDeleteNode, useNodeParlementairItem, useAddNodeStakeholder, useUpdateNodeStakeholder, useRemoveNodeStakeholder, useNodeTitleHistory, useNodeStatusHistory, useNodeBronDetail, useNodeBijlage } from '@/hooks/useNodes';
import { useTasks } from '@/hooks/useTasks';
import { usePeople } from '@/hooks/usePeople';
import { useNodeTags, useAddTagToNode, useRemoveTagFromNode, useTags } from '@/hooks/useTags';
import { useReferences } from '@/hooks/useMentions';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { NODE_TYPE_COLORS, STAKEHOLDER_ROL_LABELS, BRON_TYPE_LABELS, NodeType, formatFunctie } from '@/types';
import { uploadBijlage, deleteBijlage, getBijlageDownloadUrl, updateNodeBronDetail } from '@/api/nodes';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { formatDate } from '@/utils/dates';

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
  const location = useLocation();
  const corpusUrl = (location.state as { fromCorpus?: string } | null)?.fromCorpus ?? '/corpus';
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
  const { data: parlementairItem } = useNodeParlementairItem(nodeId, node?.node_type);
  const { data: bronDetail, refetch: refetchBronDetail } = useNodeBronDetail(nodeId, node?.node_type);
  const { data: bijlageInfo, refetch: refetchBijlage } = useNodeBijlage(nodeId, node?.node_type);
  const { data: references } = useReferences(nodeId);
  const { data: titleHistory } = useNodeTitleHistory(nodeId);
  const { data: statusHistory } = useNodeStatusHistory(nodeId);
  const { openTaskDetail } = useTaskDetail();
  const addStakeholder = useAddNodeStakeholder();
  const updateStakeholder = useUpdateNodeStakeholder();
  const removeStakeholder = useRemoveNodeStakeholder();
  const { data: allPeople } = usePeople();
  const [newStakeholderPersonId, setNewStakeholderPersonId] = useState('');
  const [newStakeholderRol, setNewStakeholderRol] = useState('betrokken');
  const [personCreateName, setPersonCreateName] = useState('');
  const [showPersonCreate, setShowPersonCreate] = useState(false);
  const [bronEditing, setBronEditing] = useState(false);
  const [bronType, setBronType] = useState('');
  const [bronAuteur, setBronAuteur] = useState('');
  const [bronPublicatieDatum, setBronPublicatieDatum] = useState('');
  const [bronUrl, setBronUrl] = useState('');
  const [bijlageUploading, setBijlageUploading] = useState(false);

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
        onClick={() => navigate(corpusUrl)}
        className="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Terug naar corpus
      </button>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Badge variant={color as 'blue'} dot title={nodeAltLabel(node.node_type)}>
              {nodeLabel(node.node_type)}
            </Badge>
            {node.status && <Badge variant="gray">{node.status}</Badge>}
          </div>
          <h1 className="text-2xl font-bold text-text">{node.title}</h1>
          <div className="flex flex-wrap items-center gap-2 sm:gap-4 mt-2 text-xs text-text-secondary">
            <span className="inline-flex items-center gap-1">
              <Calendar className="h-3.5 w-3.5" />
              Aangemaakt: {formatDate(node.created_at)}
            </span>
            <span className="inline-flex items-center gap-1">
              <LinkIcon className="h-3.5 w-3.5" />
              {node.edge_count ?? 0} verbindingen
            </span>
            {parlementairItem?.document_url && (
              <a
                href={parlementairItem.document_url}
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
      <div className="overflow-x-auto scrollbar-hide">
        <div className="flex items-center gap-1 border-b border-border">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px whitespace-nowrap flex-shrink-0',
                activeTab === tab.id
                  ? 'border-primary-900 text-primary-900'
                  : 'border-transparent text-text-secondary hover:text-text hover:border-border',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
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

            {/* Bron detail */}
            {node.node_type === NodeType.BRON && bronDetail && (
              <Card>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-text">Brongegevens</h3>
                  {!bronEditing && (
                    <button
                      onClick={() => {
                        setBronType(bronDetail.type);
                        setBronAuteur(bronDetail.auteur ?? '');
                        setBronPublicatieDatum(bronDetail.publicatie_datum ?? '');
                        setBronUrl(bronDetail.url ?? '');
                        setBronEditing(true);
                      }}
                      className="text-xs text-primary-700 hover:text-primary-900 transition-colors"
                    >
                      Bewerken
                    </button>
                  )}
                </div>
                {bronEditing ? (
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-text-secondary mb-1">Type</label>
                      <select
                        value={bronType}
                        onChange={(e) => setBronType(e.target.value)}
                        className="w-full rounded-lg border border-border bg-white px-3 py-1.5 text-sm"
                      >
                        {Object.entries(BRON_TYPE_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-text-secondary mb-1">Auteur</label>
                      <input
                        type="text"
                        value={bronAuteur}
                        onChange={(e) => setBronAuteur(e.target.value)}
                        placeholder="Naam auteur..."
                        className="w-full rounded-lg border border-border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-text-secondary mb-1">Publicatiedatum</label>
                      <input
                        type="date"
                        value={bronPublicatieDatum}
                        onChange={(e) => setBronPublicatieDatum(e.target.value)}
                        className="w-full rounded-lg border border-border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-text-secondary mb-1">URL</label>
                      <input
                        type="url"
                        value={bronUrl}
                        onChange={(e) => setBronUrl(e.target.value)}
                        placeholder="https://..."
                        className="w-full rounded-lg border border-border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={async () => {
                          await updateNodeBronDetail(nodeId, {
                            type: bronType,
                            auteur: bronAuteur || null,
                            publicatie_datum: bronPublicatieDatum || null,
                            url: bronUrl || null,
                          });
                          setBronEditing(false);
                          refetchBronDetail();
                        }}
                      >
                        Opslaan
                      </Button>
                      <Button variant="secondary" size="sm" onClick={() => setBronEditing(false)}>
                        Annuleren
                      </Button>
                    </div>
                  </div>
                ) : (
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <dt className="text-xs font-medium text-text-secondary">Type</dt>
                      <dd className="text-sm text-text mt-0.5">
                        {BRON_TYPE_LABELS[bronDetail.type] ?? bronDetail.type}
                      </dd>
                    </div>
                    {bronDetail.auteur && (
                      <div>
                        <dt className="text-xs font-medium text-text-secondary">Auteur</dt>
                        <dd className="text-sm text-text mt-0.5">{bronDetail.auteur}</dd>
                      </div>
                    )}
                    {bronDetail.publicatie_datum && (
                      <div>
                        <dt className="text-xs font-medium text-text-secondary">Publicatiedatum</dt>
                        <dd className="text-sm text-text mt-0.5">{formatDate(bronDetail.publicatie_datum)}</dd>
                      </div>
                    )}
                    {bronDetail.url && (
                      <div className="sm:col-span-2">
                        <dt className="text-xs font-medium text-text-secondary">URL</dt>
                        <dd className="text-sm mt-0.5">
                          <a
                            href={bronDetail.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary-700 hover:text-primary-900 inline-flex items-center gap-1"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                            {bronDetail.url}
                          </a>
                        </dd>
                      </div>
                    )}
                  </dl>
                )}
              </Card>
            )}

            {/* Bijlage */}
            {node.node_type === NodeType.BRON && (
              <Card>
                <h3 className="text-sm font-medium text-text mb-3">Bijlage</h3>
                {bijlageInfo ? (
                  <div className="flex items-center justify-between p-3 rounded-lg border border-border bg-gray-50/50">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="h-5 w-5 text-text-secondary shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm text-text truncate">{bijlageInfo.bestandsnaam}</p>
                        <p className="text-xs text-text-secondary">
                          {(bijlageInfo.bestandsgrootte / 1024).toFixed(1)} KB
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <a
                        href={getBijlageDownloadUrl(nodeId)}
                        className="p-1.5 rounded-lg text-primary-700 hover:bg-primary-50 transition-colors"
                        title="Downloaden"
                      >
                        <Download className="h-4 w-4" />
                      </a>
                      <button
                        onClick={async () => {
                          if (window.confirm('Bijlage verwijderen?')) {
                            await deleteBijlage(nodeId);
                            refetchBijlage();
                          }
                        }}
                        className="p-1.5 rounded-lg text-text-secondary hover:text-red-500 hover:bg-red-50 transition-colors"
                        title="Verwijderen"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-border hover:border-border-hover p-6 transition-colors cursor-pointer">
                    <input
                      type="file"
                      accept=".pdf,.doc,.docx,.odt,.txt,.png,.jpg,.jpeg"
                      disabled={bijlageUploading}
                      onChange={async (e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        setBijlageUploading(true);
                        try {
                          await uploadBijlage(nodeId, file);
                          refetchBijlage();
                        } catch (err) {
                          console.error('Upload failed', err);
                        } finally {
                          setBijlageUploading(false);
                        }
                      }}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                    <Upload className="h-6 w-6 text-text-secondary" />
                    <p className="text-sm text-text-secondary">
                      {bijlageUploading ? 'Uploaden...' : 'Sleep een bestand hierheen of klik om te uploaden'}
                    </p>
                    <p className="text-xs text-text-secondary">
                      PDF, Word, ODT, TXT, PNG, JPEG (max. 20 MB)
                    </p>
                  </div>
                )}
              </Card>
            )}

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

            {/* Add stakeholder form */}
            <Card>
              <h4 className="text-sm font-medium text-text mb-3">Betrokkene toevoegen</h4>
              <div className="flex flex-col sm:flex-row items-stretch sm:items-end gap-3">
                <div className="flex-1">
                  <CreatableSelect
                    label="Persoon"
                    value={newStakeholderPersonId}
                    onChange={setNewStakeholderPersonId}
                    options={(allPeople ?? []).map((p) => ({
                      value: p.id,
                      label: p.naam,
                      description: formatFunctie(p.functie),
                    }))}
                    placeholder="Selecteer persoon..."
                    onCreate={async (text) => {
                      setPersonCreateName(text);
                      setShowPersonCreate(true);
                      return null;
                    }}
                    createLabel="Nieuwe persoon aanmaken"
                  />
                </div>
                <div className="w-full sm:w-48">
                  <label className="block text-sm font-medium text-text mb-1.5">Rol</label>
                  <select
                    value={newStakeholderRol}
                    onChange={(e) => setNewStakeholderRol(e.target.value)}
                    className="w-full rounded-xl border border-border bg-white px-3.5 py-2.5 text-sm"
                  >
                    {Object.entries(STAKEHOLDER_ROL_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
                <Button
                  icon={<Plus className="h-4 w-4" />}
                  disabled={!newStakeholderPersonId || addStakeholder.isPending}
                  onClick={() => {
                    addStakeholder.mutate(
                      { nodeId, data: { person_id: newStakeholderPersonId, rol: newStakeholderRol } },
                      {
                        onSuccess: () => {
                          setNewStakeholderPersonId('');
                          setNewStakeholderRol('betrokken');
                        },
                      },
                    );
                  }}
                >
                  Toevoegen
                </Button>
              </div>
            </Card>

            {/* Stakeholder list */}
            {stakeholders && stakeholders.length > 0 ? (
              <div className="space-y-2">
                {stakeholders.map((s) => (
                  <div key={s.id} className="flex items-center gap-3 p-3 rounded-xl border border-border bg-white">
                    <div className="flex-1 min-w-0">
                      <PersonCardExpandable
                        person={s.person}
                      />
                    </div>
                    <select
                      value={s.rol}
                      onChange={(e) => {
                        updateStakeholder.mutate({
                          nodeId,
                          stakeholderId: s.id,
                          data: { rol: e.target.value },
                        });
                      }}
                      className="rounded-lg border border-border bg-white px-2.5 py-1.5 text-sm"
                    >
                      {Object.entries(STAKEHOLDER_ROL_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => {
                        if (window.confirm(`${s.person.naam} verwijderen als betrokkene?`)) {
                          removeStakeholder.mutate({ nodeId, stakeholderId: s.id });
                        }
                      }}
                      className="p-1.5 rounded-lg text-text-secondary hover:text-red-500 hover:bg-red-50 transition-colors"
                      title="Verwijderen"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
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
          <div className="space-y-6">
            {/* Title history */}
            <Card>
              <h3 className="text-sm font-medium text-text mb-3">Titelgeschiedenis</h3>
              {titleHistory && titleHistory.length > 0 ? (
                <div className="space-y-2">
                  {titleHistory.map((record) => (
                    <div
                      key={record.id}
                      className="flex items-center justify-between p-3 rounded-lg border border-border bg-gray-50/50"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {!record.geldig_tot ? (
                          <span className="inline-block w-2 h-2 rounded-full bg-green-500 shrink-0" title="Huidig" />
                        ) : (
                          <span className="inline-block w-2 h-2 rounded-full bg-gray-300 shrink-0" title="Vorig" />
                        )}
                        <span className="text-sm text-text truncate">{record.title}</span>
                      </div>
                      <span className="text-xs text-text-secondary shrink-0 ml-3">
                        {formatDate(record.geldig_van)}
                        {record.geldig_tot
                          ? ` — ${formatDate(record.geldig_tot)}`
                          : ' — heden'}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-text-secondary">Geen titelgeschiedenis beschikbaar.</p>
              )}
            </Card>

            {/* Status history */}
            <Card>
              <h3 className="text-sm font-medium text-text mb-3">Statusgeschiedenis</h3>
              {statusHistory && statusHistory.length > 0 ? (
                <div className="space-y-2">
                  {statusHistory.map((record) => (
                    <div
                      key={record.id}
                      className="flex items-center justify-between p-3 rounded-lg border border-border bg-gray-50/50"
                    >
                      <div className="flex items-center gap-2">
                        {!record.geldig_tot ? (
                          <span className="inline-block w-2 h-2 rounded-full bg-green-500 shrink-0" title="Huidig" />
                        ) : (
                          <span className="inline-block w-2 h-2 rounded-full bg-gray-300 shrink-0" title="Vorig" />
                        )}
                        <Badge variant="gray">{record.status}</Badge>
                      </div>
                      <span className="text-xs text-text-secondary shrink-0 ml-3">
                        {formatDate(record.geldig_van)}
                        {record.geldig_tot
                          ? ` — ${formatDate(record.geldig_tot)}`
                          : ' — heden'}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-text-secondary">Geen statusgeschiedenis beschikbaar.</p>
              )}
            </Card>
          </div>
        )}
      </div>

      {showEditForm && (
        <NodeEditForm
          open={showEditForm}
          onClose={() => setShowEditForm(false)}
          node={node}
        />
      )}

      <PersonQuickCreateForm
        open={showPersonCreate}
        onClose={() => setShowPersonCreate(false)}
        initialName={personCreateName}
        onCreated={(personId) => {
          setNewStakeholderPersonId(personId);
        }}
      />
    </div>
  );
}
