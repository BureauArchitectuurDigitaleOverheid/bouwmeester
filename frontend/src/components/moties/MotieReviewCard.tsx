import { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronUp, Check, X, ExternalLink, Users, Calendar, Plus, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/common/Badge';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import {
  useApproveSuggestedEdge,
  useRejectSuggestedEdge,
  useRejectMotieImport,
  useCompleteMotieReview,
} from '@/hooks/useMoties';
import { usePeople } from '@/hooks/usePeople';
import type { MotieImport } from '@/types';
import {
  MOTIE_IMPORT_STATUS_LABELS,
  MOTIE_IMPORT_STATUS_COLORS,
  NODE_TYPE_COLORS,
} from '@/types';
import { useVocabulary } from '@/contexts/VocabularyContext';
import type { CompleteReviewData } from '@/api/moties';

interface FollowUpTaskRow {
  title: string;
  assignee_id: string;
  deadline: string;
}

interface MotieReviewCardProps {
  motie: MotieImport;
  defaultExpanded?: boolean;
}

export function MotieReviewCard({ motie, defaultExpanded = false }: MotieReviewCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [showCompleteForm, setShowCompleteForm] = useState(false);
  const [eigenaarId, setEigenaarId] = useState('');
  const [followUpTasks, setFollowUpTasks] = useState<FollowUpTaskRow[]>([]);
  const cardRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (defaultExpanded && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [defaultExpanded]);
  const { nodeLabel, edgeLabel } = useVocabulary();
  const approveEdge = useApproveSuggestedEdge();
  const rejectEdge = useRejectSuggestedEdge();
  const rejectMotie = useRejectMotieImport();
  const completeReview = useCompleteMotieReview();
  const { data: people } = usePeople();

  const handleCompleteSubmit = () => {
    const data: CompleteReviewData = {
      eigenaar_id: eigenaarId,
      tasks: followUpTasks
        .filter((t) => t.title.trim())
        .map((t) => ({
          title: t.title,
          assignee_id: t.assignee_id || undefined,
          deadline: t.deadline || undefined,
        })),
    };
    completeReview.mutate(
      { id: motie.id, data },
      {
        onSuccess: () => {
          setShowCompleteForm(false);
          setEigenaarId('');
          setFollowUpTasks([]);
        },
      },
    );
  };

  const addTaskRow = () => {
    setFollowUpTasks([...followUpTasks, { title: '', assignee_id: '', deadline: '' }]);
  };

  const updateTaskRow = (index: number, field: keyof FollowUpTaskRow, value: string) => {
    setFollowUpTasks(followUpTasks.map((t, i) => (i === index ? { ...t, [field]: value } : t)));
  };

  const removeTaskRow = (index: number) => {
    setFollowUpTasks(followUpTasks.filter((_, i) => i !== index));
  };

  const pendingEdges = motie.suggested_edges?.filter((e) => e.status === 'pending') ?? [];
  const allEdgesReviewed = motie.suggested_edges
    ? motie.suggested_edges.every((e) => e.status !== 'pending')
    : true;

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return null;
    try {
      return new Date(dateStr).toLocaleDateString('nl-NL', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div ref={cardRef}>
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Badge
              variant={MOTIE_IMPORT_STATUS_COLORS[motie.status] as 'blue'}
            >
              {MOTIE_IMPORT_STATUS_LABELS[motie.status]}
            </Badge>
            <span className="text-xs text-text-secondary">{motie.bron === 'tweede_kamer' ? 'Tweede Kamer' : 'Eerste Kamer'}</span>
            <span className="text-xs text-text-secondary">{motie.zaak_nummer}</span>
            {motie.datum && (
              <span className="text-xs text-text-secondary flex items-center gap-0.5">
                <Calendar className="h-3 w-3" />
                {formatDate(motie.datum)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-text">{motie.onderwerp}</h3>
            {motie.document_url && (
              <a
                href={motie.document_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary-600 hover:text-primary-700 shrink-0"
                title="Bekijk op tweedekamer.nl"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
          <p className="text-xs text-text-secondary">Zaak: {motie.titel}</p>        </div>

        <div className="flex items-center gap-2 shrink-0">
          {motie.suggested_edges && motie.suggested_edges.length > 0 && (
            <span className="text-xs text-text-secondary">
              {pendingEdges.length} te beoordelen
            </span>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1 rounded hover:bg-gray-100 transition-colors"
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border space-y-4">
          {/* Indieners */}
          {motie.indieners && motie.indieners.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-text mb-1.5 flex items-center gap-1">
                <Users className="h-3.5 w-3.5" />
                Indieners
              </h4>
              <div className="flex flex-wrap gap-1">
                {motie.indieners.map((indiener) => (
                  <Badge key={indiener} variant="purple">{indiener}</Badge>
                ))}
              </div>
            </div>
          )}

          {/* Summary */}
          {motie.llm_samenvatting && (
            <div>
              <h4 className="text-xs font-medium text-text mb-1">Samenvatting</h4>
              <p className="text-sm text-text-secondary">{motie.llm_samenvatting}</p>
            </div>
          )}

          {/* Document text */}
          {motie.document_tekst && (
            <div>
              <h4 className="text-xs font-medium text-text mb-1">Motietekst</h4>
              <p className="text-sm text-text-secondary whitespace-pre-wrap bg-gray-50 rounded-lg p-3 max-h-48 overflow-y-auto">
                {motie.document_tekst}
              </p>
            </div>
          )}

          {/* Matched tags */}
          {motie.matched_tags && motie.matched_tags.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-text mb-1.5">Gematchte tags</h4>
              <div className="flex flex-wrap gap-1">
                {motie.matched_tags.map((tag) => (
                  <Badge key={tag} variant="slate">{tag}</Badge>
                ))}
              </div>
            </div>
          )}

          {/* Suggested edges */}
          {motie.suggested_edges && motie.suggested_edges.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-text mb-2">
                Voorgestelde verbindingen ({motie.suggested_edges.length})
              </h4>
              <div className="space-y-2">
                {motie.suggested_edges.map((edge) => (
                  <div
                    key={edge.id}
                    className="flex items-center gap-3 p-2 rounded-lg bg-gray-50"
                  >
                    <div className="flex-1 min-w-0">
                      {edge.target_node && (
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={NODE_TYPE_COLORS[edge.target_node.node_type] as 'blue'}
                            dot
                          >
                            {nodeLabel(edge.target_node.node_type)}
                          </Badge>
                          <button
                            onClick={() => navigate(`/nodes/${edge.target_node_id}`)}
                            className="text-sm text-text hover:text-primary-700 truncate transition-colors"
                          >
                            {edge.target_node.title}
                          </button>
                        </div>
                      )}
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="slate">
                          {edgeLabel(edge.edge_type_id)}
                        </Badge>
                        <span className="text-xs text-text-secondary">
                          {Math.round(edge.confidence * 100)}%
                        </span>
                        {edge.reason && (
                          <span className="text-xs text-text-secondary">
                            — {edge.reason}
                          </span>
                        )}
                      </div>
                    </div>

                    {edge.status === 'pending' ? (
                      <div className="flex items-center gap-1 shrink-0">
                        <button
                          onClick={() => approveEdge.mutate(edge.id)}
                          className="p-1.5 rounded-lg bg-green-50 text-green-600 hover:bg-green-100 transition-colors"
                          title="Goedkeuren"
                        >
                          <Check className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => rejectEdge.mutate(edge.id)}
                          className="p-1.5 rounded-lg bg-red-50 text-red-600 hover:bg-red-100 transition-colors"
                          title="Afwijzen"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    ) : (
                      <Badge variant={edge.status === 'approved' ? 'green' : 'gray'}>
                        {edge.status === 'approved' ? 'Goedgekeurd' : 'Afgewezen'}
                      </Badge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-2">
            {motie.status === 'imported' && allEdgesReviewed && !showCompleteForm && (
              <Button
                size="sm"
                onClick={() => setShowCompleteForm(true)}
              >
                Beoordeling afronden
              </Button>
            )}
            {motie.status === 'imported' && (
              <Button
                size="sm"
                variant="ghost"
                className="text-red-500 hover:bg-red-50"
                onClick={() => rejectMotie.mutate(motie.id)}
              >
                Niet relevant
              </Button>
            )}
            {motie.corpus_node_id && (
              <Button
                size="sm"
                variant="secondary"
                icon={<ExternalLink className="h-3.5 w-3.5" />}
                onClick={() => navigate(`/nodes/${motie.corpus_node_id}`)}
              >
                Bekijk node
              </Button>
            )}
            {motie.document_url && (
              <a
                href={motie.document_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<ExternalLink className="h-3.5 w-3.5" />}
                >
                  Bekijk op tweedekamer.nl
                </Button>
              </a>
            )}
          </div>

          {/* Inline completion form */}
          {showCompleteForm && (
            <div className="mt-4 p-4 rounded-xl border border-primary-200 bg-primary-50/50 space-y-4">
              <h4 className="text-sm font-semibold text-text">Beoordeling afronden</h4>

              {/* Eigenaar selector */}
              <div className="max-w-sm">
                <CreatableSelect
                  label="Eigenaar toewijzen"
                  value={eigenaarId}
                  onChange={setEigenaarId}
                  options={(people ?? []).map((p) => ({
                    value: p.id,
                    label: p.naam,
                    description: p.functie || undefined,
                  }))}
                  placeholder="Selecteer eigenaar..."
                  required
                />
              </div>

              {/* Follow-up tasks */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h5 className="text-xs font-medium text-text">Vervolgacties</h5>
                  <button
                    onClick={addTaskRow}
                    className="text-xs text-primary-700 hover:text-primary-800 flex items-center gap-1"
                  >
                    <Plus className="h-3 w-3" />
                    Taak toevoegen
                  </button>
                </div>
                {followUpTasks.length > 0 && (
                  <div className="space-y-2">
                    {followUpTasks.map((task, index) => (
                      <div key={index} className="flex items-start gap-2 p-2 rounded-lg bg-white border border-border">
                        <div className="flex-1 space-y-2">
                          <input
                            type="text"
                            value={task.title}
                            onChange={(e) => updateTaskRow(index, 'title', e.target.value)}
                            placeholder="Omschrijving taak..."
                            className="w-full rounded-lg border border-border px-3 py-1.5 text-sm"
                          />
                          <div className="flex gap-2">
                            <div className="flex-1">
                              <CreatableSelect
                                value={task.assignee_id}
                                onChange={(v) => updateTaskRow(index, 'assignee_id', v)}
                                options={(people ?? []).map((p) => ({
                                  value: p.id,
                                  label: p.naam,
                                  description: p.functie || undefined,
                                }))}
                                placeholder="Toewijzen aan..."
                              />
                            </div>
                            <input
                              type="date"
                              value={task.deadline}
                              onChange={(e) => updateTaskRow(index, 'deadline', e.target.value)}
                              className="rounded-lg border border-border px-3 py-1.5 text-sm"
                            />
                          </div>
                        </div>
                        <button
                          onClick={() => removeTaskRow(index)}
                          className="p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors mt-1"
                          title="Verwijderen"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Form buttons */}
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  onClick={handleCompleteSubmit}
                  disabled={!eigenaarId || completeReview.isPending}
                  loading={completeReview.isPending}
                >
                  Afronden
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setShowCompleteForm(false);
                    setEigenaarId('');
                    setFollowUpTasks([]);
                  }}
                >
                  Annuleren
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
    </div>
  );
}
