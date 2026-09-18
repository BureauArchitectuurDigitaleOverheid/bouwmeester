import { useState, useRef, useCallback } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { Badge } from '@/components/common/Badge';
import { Button } from '@/components/common/Button';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { RichTextDisplay } from '@/components/common/RichTextDisplay';
import { Select } from '@/components/common/Select';
import { Input } from '@/components/common/Input';
import { DetailMetadataGrid } from '@/components/common/DetailMetadataGrid';
import { FileUpload } from '@/components/common/FileUpload';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import { PersonCardExpandable } from '@/components/people/PersonCardExpandable';
import { PersonQuickCreateForm } from '@/components/people/PersonQuickCreateForm';
import { Icon } from '@/components/nldd/Icon';
import { NlddButton } from '@/components/nldd/NlddLink';
import { useNlddEvent } from '@/components/nldd/events';
import { NodeEditForm } from './NodeEditForm';
import { EdgeList } from './EdgeList';
import { BeleidskompasPanel } from './beleidskompas/BeleidskompasPanel';
import { FinancieelOverzichtPanel } from '@/components/financieel/FinancieelOverzichtPanel';
import { TaskView } from '@/components/tasks/TaskView';
import { useNode, useNodeNeighbors, useNodeStakeholders, useDeleteNode, useNodeParlementairItem, useAddNodeStakeholder, useUpdateNodeStakeholder, useRemoveNodeStakeholder, useNodeTitleHistory, useNodeStatusHistory, useNodeBronDetail, useNodeBijlage } from '@/hooks/useNodes';
import { useTasks } from '@/hooks/useTasks';
import { usePeople } from '@/hooks/usePeople';
import { useNodeTags, useAddTagToNode, useRemoveTagFromNode, useTags } from '@/hooks/useTags';
import { useReferences } from '@/hooks/useMentions';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { NODE_TYPE_COLORS, NODE_STATUS_LABELS, STAKEHOLDER_ROL_LABELS, BRON_TYPE_LABELS, NodeType, type NodeStatus, formatFunctie, titleCase } from '@/types';
import { uploadBijlage, deleteBijlage, getBijlageDownloadUrl, updateNodeBronDetail } from '@/api/nodes';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { useToast } from '@/contexts/ToastContext';
import { formatDate } from '@/utils/dates';
import { StakeholderTab } from '@/components/stakeholders/StakeholderTab';

/** A single removable tag chip: `nldd-token` with its `dismiss` event bridged to React. */
function NlddTagToken({ text, onDismiss }: { text: string; onDismiss: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'dismiss', onDismiss);
  return <nldd-token ref={ref} text={text} control="dismiss" dismiss-text={`Verwijder tag ${text}`} />;
}

/** An `nldd-list-item[button]` row with its click bridged to React. */
function ClickableListItem({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick);
  return (
    <nldd-list-item ref={ref} button>
      {children}
    </nldd-list-item>
  );
}

/** An `nldd-link` with its click bridged to React, for an in-page action rather than navigation. */
function ActionLink({ text, onClick }: { text: string; onClick: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick);
  return <nldd-link ref={ref} text={text} size="xs" />;
}

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
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as TabId | null;
  const activeTab: TabId = tabParam && tabs.some((t) => t.id === tabParam) ? tabParam : 'overview';
  const setActiveTab = useCallback((tab: TabId) => {
    setSearchParams(tab === 'overview' ? {} : { tab }, { replace: true });
  }, [setSearchParams]);
  const tabBarRef = useRef<HTMLElement>(null);
  const handleTabChange = useCallback(
    (event: Event) => {
      const item = (event as CustomEvent<{ item?: HTMLElement }>).detail?.item;
      const tabId = item?.dataset.tabId as TabId | undefined;
      if (tabId) setActiveTab(tabId);
    },
    [setActiveTab],
  );
  useNlddEvent(tabBarRef, 'tabchange', handleTabChange);
  const [showEditForm, setShowEditForm] = useState(false);
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
  const { showError } = useToast();
  const [newStakeholderPersonId, setNewStakeholderPersonId] = useState('');
  const [newStakeholderRol, setNewStakeholderRol] = useState('betrokken');
  const [personCreateName, setPersonCreateName] = useState('');
  const [showPersonCreate, setShowPersonCreate] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showBijlageDeleteConfirm, setShowBijlageDeleteConfirm] = useState(false);
  const [removeStakeholderId, setRemoveStakeholderId] = useState<{ id: string; naam: string } | null>(null);
  const [bronEditing, setBronEditing] = useState(false);
  const [bronType, setBronType] = useState('');
  const [bronAuteur, setBronAuteur] = useState('');
  const [bronPublicatieDatum, setBronPublicatieDatum] = useState('');
  const [bronUrl, setBronUrl] = useState('');
  const [bijlageUploading, setBijlageUploading] = useState(false);

  const { data: allTags } = useTags();
  const existingTagIds = new Set(nodeTags?.map((nt) => nt.tag.id) ?? []);

  const handleSelectTag = useCallback((tagId: string) => {
    addTag.mutate({ nodeId, data: { tag_id: tagId } });
  }, [addTag, nodeId]);

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
    await deleteNode.mutateAsync(node.id);
    setShowDeleteConfirm(false);
    navigate('/corpus');
  };

  return (
    <div className="space-y-6">
      {/* Back button */}
      <NlddButton
        variant="neutral-transparent"
        size="sm"
        text="Terug naar corpus"
        startIcon="arrow-left"
        onClick={() => navigate(corpusUrl)}
      />

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Badge variant={color} dot title={nodeAltLabel(node.node_type)}>
              {nodeLabel(node.node_type)}
            </Badge>
            {node.status && <Badge variant="gray">{NODE_STATUS_LABELS[node.status as NodeStatus] ?? node.status}</Badge>}
          </div>
          <h1 className="text-2xl font-bold text-text">{node.title}</h1>
          <div className="flex flex-wrap items-center gap-2 sm:gap-4 mt-2 text-xs text-text-secondary">
            <span className="inline-flex items-center gap-1">
              <Icon name="calendar" size="xs" />
              Aangemaakt: {formatDate(node.created_at)}
            </span>
            <span className="inline-flex items-center gap-1">
              <Icon name="link" size="xs" />
              {node.edge_count ?? 0} verbindingen
            </span>
            {parlementairItem?.document_url && (
              <nldd-link
                href={parlementairItem.document_url}
                target="_blank"
                text="Bekijk op tweedekamer.nl"
                start-icon="external-link"
              />
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button variant="secondary" size="sm" icon="pencil" onClick={() => setShowEditForm(true)}>
            Bewerken
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon="trash"
            onClick={() => setShowDeleteConfirm(true)}
            className="text-red-500 hover:bg-red-50 hover:text-red-600"
          >
            Verwijder
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <nldd-tab-bar ref={tabBarRef} variant="text" accessible-label="Node-secties">
        {tabs.map((tab) => (
          <nldd-tab-bar-item
            key={tab.id}
            text={tab.label}
            data-tab-id={tab.id}
            current={activeTab === tab.id ? true : undefined}
          />
        ))}
      </nldd-tab-bar>

      {/* Tab content */}
      <div>
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Beleidskompas panel for dossier nodes */}
            {node.node_type === 'dossier' && (
              <BeleidskompasPanel
                nodeId={nodeId}
                stakeholderCount={stakeholders?.length ?? 0}
                onNavigateToStakeholders={() => setActiveTab('stakeholders')}
              />
            )}

            {/* Description */}
            <Card>
              <h3 className="text-sm font-medium text-text mb-2">Beschrijving</h3>
              <RichTextDisplay content={node.description} />
            </Card>

            {/* Financieel overzicht for instrument/maatregel/doel nodes */}
            {(node.node_type === NodeType.INSTRUMENT || node.node_type === NodeType.MAATREGEL || node.node_type === NodeType.DOEL) && (
              <Card>
                <h3 className="text-sm font-medium text-text mb-3">Financieel overzicht</h3>
                <FinancieelOverzichtPanel nodeId={nodeId} nodeType={node.node_type} />
              </Card>
            )}

            {/* Bron detail */}
            {node.node_type === NodeType.BRON && bronDetail && (
              <Card>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-text">Brongegevens</h3>
                  {!bronEditing && (
                    <ActionLink
                      text="Bewerken"
                      onClick={() => {
                        setBronType(bronDetail.type);
                        setBronAuteur(bronDetail.auteur ?? '');
                        setBronPublicatieDatum(bronDetail.publicatie_datum ?? '');
                        setBronUrl(bronDetail.url ?? '');
                        setBronEditing(true);
                      }}
                    />
                  )}
                </div>
                {bronEditing ? (
                  <div className="space-y-3">
                    <Select
                      label="Type"
                      value={bronType}
                      onChange={(e) => setBronType(e.target.value)}
                      options={Object.entries(BRON_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
                    />
                    <Input
                      label="Auteur"
                      type="text"
                      value={bronAuteur}
                      onChange={(e) => setBronAuteur(e.target.value)}
                      placeholder="Naam auteur..."
                    />
                    <Input
                      label="Publicatiedatum"
                      type="date"
                      value={bronPublicatieDatum}
                      onChange={(e) => setBronPublicatieDatum(e.target.value)}
                    />
                    <Input
                      label="URL"
                      type="url"
                      value={bronUrl}
                      onChange={(e) => setBronUrl(e.target.value)}
                      placeholder="https://..."
                    />
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={async () => {
                          try {
                            await updateNodeBronDetail(nodeId, {
                              type: bronType,
                              auteur: bronAuteur || null,
                              publicatie_datum: bronPublicatieDatum || null,
                              url: bronUrl || null,
                            });
                            setBronEditing(false);
                            refetchBronDetail();
                          } catch (err) {
                            console.error('Fout bij opslaan brongegevens:', err);
                            showError('Fout bij opslaan brongegevens. Probeer het opnieuw.');
                          }
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
                  <DetailMetadataGrid
                    items={[
                      { label: 'Type', value: BRON_TYPE_LABELS[bronDetail.type] ?? bronDetail.type },
                      { label: 'Auteur', value: bronDetail.auteur },
                      {
                        label: 'Publicatiedatum',
                        value: bronDetail.publicatie_datum ? formatDate(bronDetail.publicatie_datum) : undefined,
                      },
                      {
                        label: 'URL',
                        span: 2,
                        value: bronDetail.url ? (
                          bronDetail.url.startsWith('http://') || bronDetail.url.startsWith('https://') ? (
                            <nldd-link href={bronDetail.url} target="_blank" text={bronDetail.url} start-icon="external-link" />
                          ) : (
                            <span className="text-text-secondary">{bronDetail.url}</span>
                          )
                        ) : undefined,
                      },
                    ]}
                  />
                )}
              </Card>
            )}

            {/* Bijlage */}
            {node.node_type === NodeType.BRON && (
              <Card>
                <h3 className="text-sm font-medium text-text mb-3">Bijlage</h3>
                {bijlageInfo ? (
                  <nldd-list variant="box-tinted" dividers="never">
                    <nldd-list-item>
                      <nldd-icon-cell icon="file-text" />
                      <nldd-title-cell
                        text={bijlageInfo.bestandsnaam}
                        color={!bijlageInfo.bestand_beschikbaar ? 'critical' : undefined}
                        overline={
                          !bijlageInfo.bestand_beschikbaar
                            ? 'Bestand niet beschikbaar'
                            : bijlageInfo.bestandsgrootte >= 1024 * 1024
                              ? `${(bijlageInfo.bestandsgrootte / (1024 * 1024)).toFixed(1)} MB`
                              : `${(bijlageInfo.bestandsgrootte / 1024).toFixed(1)} KB`
                        }
                      />
                      {bijlageInfo.bestand_beschikbaar && (
                        <NlddIconButton
                          icon="download"
                          variant="neutral-transparent"
                          size="sm"
                          accessibleLabel="Downloaden"
                          onClick={() => window.open(getBijlageDownloadUrl(nodeId), '_blank')}
                        />
                      )}
                      <NlddIconButton
                        icon="trash"
                        variant="critical-transparent"
                        size="sm"
                        accessibleLabel="Verwijderen"
                        onClick={() => setShowBijlageDeleteConfirm(true)}
                      />
                    </nldd-list-item>
                  </nldd-list>
                ) : (
                  <FileUpload
                    accept=".pdf,.doc,.docx,.odt,.txt,.png,.jpg,.jpeg"
                    disabled={bijlageUploading}
                    label={bijlageUploading ? 'Uploaden...' : 'Sleep een bestand hierheen of klik om te uploaden (PDF, Word, ODT, TXT, PNG, JPEG, max. 20 MB)'}
                    onFileSelect={async (file) => {
                      setBijlageUploading(true);
                      try {
                        await uploadBijlage(nodeId, file);
                        refetchBijlage();
                      } catch (err) {
                        const msg = err instanceof Error ? err.message : 'Onbekende fout';
                        showError(`Upload mislukt: ${msg}`);
                      } finally {
                        setBijlageUploading(false);
                      }
                    }}
                  />
                )}
              </Card>
            )}

            {/* Tags */}
            <Card>
              <h3 className="text-sm font-medium text-text mb-3">Tags</h3>
              <div className="flex flex-wrap gap-1.5 mb-3">
                {nodeTags?.map((nt) => (
                  <NlddTagToken
                    key={nt.id}
                    text={nt.tag.name}
                    onDismiss={() => removeTag.mutate({ nodeId, tagId: nt.tag.id })}
                  />
                ))}
                {(!nodeTags || nodeTags.length === 0) && (
                  <nldd-text size="xs" color="secondary">Geen tags</nldd-text>
                )}
              </div>
              {/* Add tag: search existing or create a new one */}
              <CreatableSelect
                value=""
                onChange={handleSelectTag}
                options={(allTags ?? [])
                  .filter((t) => !existingTagIds.has(t.id))
                  .map((t) => ({ value: t.id, label: t.name }))}
                placeholder="Tag zoeken of toevoegen..."
                onCreate={async (text) => {
                  addTag.mutate({ nodeId, data: { tag_name: text } });
                  return null;
                }}
              />
            </Card>

            {/* Verwijzingen (back-references from mentions) */}
            {references && references.length > 0 && (
              <Card>
                <h3 className="text-sm font-medium text-text mb-3">
                  <Icon name="link" size="sm" className="inline mr-1.5 -mt-0.5" />
                  Verwijzingen ({references.length})
                </h3>
                <nldd-list variant="box-tinted" dividers="never">
                  {references.map((ref) => (
                    <ClickableListItem
                      key={`${ref.source_type}-${ref.source_id}`}
                      onClick={() => {
                        if (ref.source_type === 'node') navigate(`/nodes/${ref.source_id}`);
                        else if (ref.source_type === 'task') openTaskDetail(ref.source_id);
                      }}
                    >
                      <nldd-text-cell width="fit-content">
                        <Badge variant="gray">
                          {ref.source_type === 'node' ? 'Node' : ref.source_type === 'task' ? 'Taak' : ref.source_type}
                        </Badge>
                      </nldd-text-cell>
                      <nldd-text-cell text={ref.source_title} />
                    </ClickableListItem>
                  ))}
                </nldd-list>
              </Card>
            )}

            {/* Metadata */}
            {node.metadata && Object.keys(node.metadata).length > 0 && (
              <Card>
                <h3 className="text-sm font-medium text-text mb-3">Metadata</h3>
                <DetailMetadataGrid
                  items={Object.entries(node.metadata).map(([key, value]) => ({
                    label: titleCase(key.replace(/_/g, ' ')),
                    value: String(value),
                  }))}
                />
              </Card>
            )}

            {/* Stakeholders preview */}
            {stakeholders && stakeholders.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-text mb-3">
                  <Icon name="users" size="sm" className="inline mr-1.5 -mt-0.5" />
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
                    <ActionLink
                      text={`Bekijk alle ${stakeholders.length} betrokkenen`}
                      onClick={() => setActiveTab('stakeholders')}
                    />
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
                <nldd-list variant="box-tinted" dividers="never">
                  {neighbors.slice(0, 5).map((neighbor) => (
                    <ClickableListItem key={neighbor.id} onClick={() => navigate(`/nodes/${neighbor.id}`)}>
                      <nldd-text-cell width="fit-content">
                        <Badge variant={NODE_TYPE_COLORS[neighbor.node_type]} dot title={nodeAltLabel(neighbor.node_type)}>
                          {nodeLabel(neighbor.node_type)}
                        </Badge>
                      </nldd-text-cell>
                      <nldd-text-cell text={neighbor.title} />
                    </ClickableListItem>
                  ))}
                </nldd-list>
                {neighbors.length > 5 && (
                  <ActionLink
                    text={`Bekijk alle ${neighbors.length} verbindingen`}
                    onClick={() => setActiveTab('connections')}
                  />
                )}
              </Card>
            )}

          </div>
        )}

        {activeTab === 'connections' && (
          <EdgeList nodeId={nodeId} nodeType={node.node_type} />
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
                  <Select
                    label="Rol"
                    value={newStakeholderRol}
                    onChange={(e) => setNewStakeholderRol(e.target.value)}
                    options={Object.entries(STAKEHOLDER_ROL_LABELS).map(([value, label]) => ({ value, label }))}
                  />
                </div>
                <Button
                  icon="plus"
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
                    <div className="w-48">
                      <Select
                        value={s.rol}
                        onChange={(e) => {
                          updateStakeholder.mutate({
                            nodeId,
                            stakeholderId: s.id,
                            data: { rol: e.target.value },
                          });
                        }}
                        options={Object.entries(STAKEHOLDER_ROL_LABELS).map(([value, label]) => ({ value, label }))}
                      />
                    </div>
                    <NlddIconButton
                      icon="trash"
                      variant="critical-transparent"
                      size="sm"
                      accessibleLabel="Verwijderen"
                      onClick={() => setRemoveStakeholderId({ id: s.id, naam: s.person.naam })}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="Geen betrokkenen"
                description="Er zijn nog geen personen gekoppeld aan deze node."
              />
            )}

            <div className="pt-4 mt-4 border-t border-border">
              <h4 className="text-sm font-medium text-text mb-2">
                Belang, houding & invloed
              </h4>
              <p className="text-xs text-text-secondary mb-3">
                Inschatting per stakeholder, los van rol. Aparte assessment voor
                analyse-doeleinden.
              </p>
              <StakeholderTab scopeType="corpus_node" scopeId={nodeId} />
            </div>
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
                <nldd-list dividers="never">
                  {titleHistory.map((record, idx) => (
                    <nldd-list-item key={record.id}>
                      <nldd-timeline-track-cell
                        status={!record.geldig_tot ? 'current' : 'past'}
                        direction="up"
                        position={
                          titleHistory.length === 1
                            ? 'only'
                            : idx === 0
                              ? 'first'
                              : idx === titleHistory.length - 1
                                ? 'last'
                                : 'between'
                        }
                      />
                      <nldd-text-cell text={record.title} />
                      <nldd-text-cell
                        color="secondary"
                        horizontal-alignment="right"
                        text={
                          record.geldig_tot
                            ? `${formatDate(record.geldig_van)} — ${formatDate(record.geldig_tot)}`
                            : `${formatDate(record.geldig_van)} — heden`
                        }
                      />
                    </nldd-list-item>
                  ))}
                </nldd-list>
              ) : (
                <nldd-text size="sm" color="secondary">Geen titelgeschiedenis beschikbaar.</nldd-text>
              )}
            </Card>

            {/* Status history */}
            <Card>
              <h3 className="text-sm font-medium text-text mb-3">Statusgeschiedenis</h3>
              {statusHistory && statusHistory.length > 0 ? (
                <nldd-list dividers="never">
                  {statusHistory.map((record, idx) => (
                    <nldd-list-item key={record.id}>
                      <nldd-timeline-track-cell
                        status={!record.geldig_tot ? 'current' : 'past'}
                        direction="up"
                        position={
                          statusHistory.length === 1
                            ? 'only'
                            : idx === 0
                              ? 'first'
                              : idx === statusHistory.length - 1
                                ? 'last'
                                : 'between'
                        }
                      />
                      <nldd-text-cell>
                        <Badge variant="gray">{NODE_STATUS_LABELS[record.status as NodeStatus] ?? record.status}</Badge>
                      </nldd-text-cell>
                      <nldd-text-cell
                        color="secondary"
                        horizontal-alignment="right"
                        text={
                          record.geldig_tot
                            ? `${formatDate(record.geldig_van)} — ${formatDate(record.geldig_tot)}`
                            : `${formatDate(record.geldig_van)} — heden`
                        }
                      />
                    </nldd-list-item>
                  ))}
                </nldd-list>
              ) : (
                <nldd-text size="sm" color="secondary">Geen statusgeschiedenis beschikbaar.</nldd-text>
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

      <ConfirmDialog
        open={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDelete}
        title="Node verwijderen"
        confirmLabel="Verwijderen"
        variant="danger"
        loading={deleteNode.isPending}
      >
        <p>Weet je zeker dat je <strong>{node.title}</strong> wilt verwijderen?</p>
        {((neighbors && neighbors.length > 0) || (nodeTasks && nodeTasks.length > 0)) && (
          <ul className="mt-2 space-y-1 list-disc list-inside">
            {neighbors && neighbors.length > 0 && (
              <li>{neighbors.length} verbinding(en) worden verwijderd</li>
            )}
            {nodeTasks && nodeTasks.length > 0 && (
              <li>{nodeTasks.length} gekoppelde taak/taken worden verwijderd</li>
            )}
          </ul>
        )}
      </ConfirmDialog>

      <ConfirmDialog
        open={showBijlageDeleteConfirm}
        onClose={() => setShowBijlageDeleteConfirm(false)}
        onConfirm={async () => {
          try {
            await deleteBijlage(nodeId);
            refetchBijlage();
            setShowBijlageDeleteConfirm(false);
          } catch {
            showError('Bijlage verwijderen mislukt.');
          }
        }}
        title="Bijlage verwijderen"
        confirmLabel="Verwijderen"
        variant="danger"
      >
        <p>Weet je zeker dat je de bijlage <strong>{bijlageInfo?.bestandsnaam}</strong> wilt verwijderen?</p>
      </ConfirmDialog>

      <ConfirmDialog
        open={!!removeStakeholderId}
        onClose={() => setRemoveStakeholderId(null)}
        onConfirm={() => {
          if (removeStakeholderId) {
            removeStakeholder.mutate({ nodeId, stakeholderId: removeStakeholderId.id });
            setRemoveStakeholderId(null);
          }
        }}
        title="Betrokkene verwijderen"
        confirmLabel="Verwijderen"
        variant="danger"
      >
        <p>Weet je zeker dat je <strong>{removeStakeholderId?.naam}</strong> wilt verwijderen als betrokkene?</p>
      </ConfirmDialog>
    </div>
  );
}
