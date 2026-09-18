import { useState } from 'react';
import { clsx } from 'clsx';
import { Link } from 'react-router-dom';
import { Card } from '@/components/common/Card';
import { Badge } from '@/components/common/Badge';
import { SendMessageModal } from '@/components/common/SendMessageModal';
import { PersonAvatar } from '@/components/people/PersonAvatar';
import { Icon } from '@/components/nldd/Icon';
import { NlddButton } from '@/components/nldd/NlddLink';
import { usePersonSummary, usePersonOrganisaties, useUpdatePersonOrganisatie, useRemovePersonOrganisatie } from '@/hooks/usePeople';
import { useSamenwerkingsverbandenForPerson } from '@/hooks/useSamenwerkingsverbanden';
import { SAMENWERKINGSVERBAND_TYPE_LABELS, SAMENWERKINGSVERBAND_TYPE_BADGE_COLORS } from '@/types';
import { useCopyToClipboard } from '@/hooks/useCopyToClipboard';
import { formatFunctie, NODE_TYPE_COLORS, STAKEHOLDER_ROL_LABELS, DIENSTVERBAND_LABELS, PHONE_LABELS, TASK_PRIORITY_LABELS } from '@/types';
import { richTextToPlain } from '@/utils/richtext';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { formatDateShort, todayISO } from '@/utils/dates';
import { useTaskDetail } from '@/contexts/TaskDetailContext';
import { useNodeDetail } from '@/contexts/NodeDetailContext';
import type { Person } from '@/types';

/** Priority -> the five semantic tag colors, for the task dot in the open-tasks list. */
const PRIORITY_DOT_COLORS: Record<string, 'critical' | 'warning' | 'accent' | 'neutral'> = {
  kritiek: 'critical',
  hoog: 'warning',
  normaal: 'accent',
  laag: 'neutral',
};

interface PersonCardExpandableProps {
  person: Person;
  onEditPerson?: (person: Person) => void;
  onDragStartPerson?: (e: React.DragEvent, person: Person) => void;
  isManager?: boolean;
  /** Override the manager badge label (e.g. "Coördinator" for teams) */
  managerLabel?: string;
  /** Extra badge shown on the right side (e.g. stakeholder role) */
  extraBadge?: React.ReactNode;
  /** Show end/delete buttons on placements (only on person/org pages) */
  showPlacementActions?: boolean;
}

export function PersonCardExpandable({ person, onEditPerson, onDragStartPerson, isManager, managerLabel, extraBadge, showPlacementActions }: PersonCardExpandableProps) {
  const [expanded, setExpanded] = useState(false);
  const { copied, copy } = useCopyToClipboard(1500);
  const [messageOpen, setMessageOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const { nodeLabel } = useVocabulary();
  const { openTaskDetail } = useTaskDetail();
  const { openNodeDetail } = useNodeDetail();
  const { data: summary, isLoading: summaryLoading } = usePersonSummary(expanded ? person.id : null);
  const { data: placements } = usePersonOrganisaties(expanded ? person.id : null);
  const { data: lidmaatschappen } = useSamenwerkingsverbandenForPerson(
    expanded ? person.id : null,
  );
  const endPlacement = useUpdatePersonOrganisatie();
  const removePlacement = useRemovePersonOrganisatie();

  const displayEmail = person.default_email || person.email;
  const handleCopyEmail = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (displayEmail) {
      copy(displayEmail);
    }
  };

  return (
    <Card
      hoverable
      onClick={() => setExpanded(!expanded)}
      draggable={!!onDragStartPerson}
      onDragStart={onDragStartPerson ? (e: React.DragEvent) => onDragStartPerson(e, person) : undefined}
    >
      <div className="flex items-center gap-3">
        <PersonAvatar person={person} size="32" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-text truncate">
              {person.naam}
            </p>
            {person.is_agent && <Badge variant="purple">Agent</Badge>}
            {isManager && (() => {
              const label = managerLabel ?? 'Manager';
              return (
                <Badge variant={label === 'Bewindspersoon' ? 'purple' : 'blue'}>
                  {label}
                </Badge>
              );
            })()}
            {extraBadge && <div className="shrink-0 ml-auto">{extraBadge}</div>}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-text-secondary mt-0.5">
            {displayEmail && (
              <button
                className="flex items-center gap-1 hover:text-primary-600 transition-colors truncate"
                onClick={handleCopyEmail}
                title="Klik om e-mail te kopiëren"
              >
                <Icon name="Mail" size="xs" />
                <span className="truncate">{copied ? 'Gekopieerd!' : displayEmail}</span>
              </button>
            )}
            {person.default_phone && (
              <a
                href={`tel:${person.default_phone}`}
                className="flex items-center gap-1 hover:text-primary-600 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                <Icon name="Phone" size="xs" />
                {person.default_phone}
              </a>
            )}
            {person.functie && !person.is_agent && (
              <span className="flex items-center gap-1 hidden sm:flex">
                <Icon name="Briefcase" size="xs" />
                <span className="truncate">{formatFunctie(person.functie)}</span>
              </span>
            )}
            {person.description && person.is_agent && (
              <span className={clsx('flex items-start gap-1', !expanded && 'truncate')}>
                <Icon name="Briefcase" size="xs" className="mt-0.5" />
                <span className={expanded ? 'whitespace-normal' : 'truncate'}>{richTextToPlain(person.description)}</span>
              </span>
            )}
            {/* Externe links: TK OData, Wikidata */}
            {expanded && (person.tk_persoon_id || person.wikidata_qid) && (
              <div className="flex items-center gap-3 text-[11px]">
                {person.tk_persoon_id && (
                  <a
                    href={`https://www.tweedekamer.nl/kamerleden_en_commissies/alle_kamerleden/${person.tk_persoon_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary-600 hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Tweede Kamer ↗
                  </a>
                )}
                {person.wikidata_qid && (
                  <a
                    href={`https://www.wikidata.org/wiki/${person.wikidata_qid}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary-600 hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Wikidata {person.wikidata_qid} ↗
                  </a>
                )}
              </div>
            )}
          </div>
        </div>
        {/* Prominent message/prompt button — always visible. The card wraps
            everything in its own click-to-expand handler, and nldd-button's
            click bubbles same as a native button would, so this is stopped
            at capture before it reaches the card. */}
        <div className="shrink-0" onClickCapture={(e) => e.stopPropagation()}>
          <NlddButton
            text={person.is_agent ? 'Prompt' : 'Bericht'}
            startIcon={person.is_agent ? 'terminal' : 'message-rectangle-text'}
            variant="neutral-tinted"
            size="sm"
            onClick={() => setMessageOpen(true)}
          />
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="mt-3 pt-3 border-t border-border text-xs">
          {/* All emails */}
          {person.emails && person.emails.length > 0 && (
            <div className="mb-3">
              <p className="text-text-secondary font-medium mb-1 flex items-center gap-1">
                <Icon name="Mail" size="xs" />
                E-mailadressen
              </p>
              <div className="space-y-0.5">
                {person.emails.map((em) => (
                  <div key={em.id} className="flex items-center gap-1.5 text-text">
                    <a
                      href={`mailto:${em.email}`}
                      className="hover:text-primary-600 transition-colors truncate"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {em.email}
                    </a>
                    {em.is_default && <Icon name="Star" size="xs" className="text-amber-500 shrink-0" />}
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* All phones */}
          {person.phones && person.phones.length > 0 && (
            <div className="mb-3">
              <p className="text-text-secondary font-medium mb-1 flex items-center gap-1">
                <Icon name="Phone" size="xs" />
                Telefoonnummers
              </p>
              <div className="space-y-0.5">
                {person.phones.map((ph) => (
                  <div key={ph.id} className="flex items-center gap-1.5 text-text">
                    <a
                      href={`tel:${ph.phone_number}`}
                      className="hover:text-primary-600 transition-colors"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {ph.phone_number}
                    </a>
                    <span className="text-text-secondary">
                      {PHONE_LABELS[ph.label] || ph.label}
                    </span>
                    {ph.is_default && <Icon name="Star" size="xs" className="text-amber-500 shrink-0" />}
                  </div>
                ))}
              </div>
            </div>
          )}
          {summaryLoading ? (
            <div className="flex items-center gap-2 text-text-secondary py-1">
              <nldd-activity-indicator size="16" />
              <span>Laden...</span>
            </div>
          ) : summary ? (
            <div className="space-y-3">
              {/* Tasks section */}
              <div>
                <div className="flex items-center gap-3 text-text-secondary">
                  <span className="flex items-center gap-1">
                    <Icon name="Circle" size="xs" />
                    {summary.open_task_count} open
                  </span>
                  <span className="flex items-center gap-1">
                    <Icon name="CheckCircle2" size="xs" />
                    {summary.done_task_count} afgerond
                  </span>
                </div>
                {summary.open_tasks.length > 0 && (
                  <div className="mt-1.5 space-y-1">
                    {summary.open_tasks.map((task) => (
                      <button
                        key={task.id}
                        className="flex items-center gap-2 text-text w-full text-left hover:text-primary-600 transition-colors rounded px-1 -mx-1 py-0.5 hover:bg-primary-50/50"
                        onClick={(e) => {
                          e.stopPropagation();
                          openTaskDetail(task.id);
                        }}
                      >
                        <nldd-tag
                          size="sm"
                          color={PRIORITY_DOT_COLORS[task.priority] ?? 'neutral'}
                          icon="circle-filled-extra-small"
                          variant="icon"
                          accessible-label={TASK_PRIORITY_LABELS[task.priority] ?? task.priority}
                        />
                        <span className="truncate">{task.title}</span>
                        {task.due_date && (
                          <span className="text-text-secondary shrink-0 ml-auto">
                            {formatDateShort(task.due_date)}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Stakeholder nodes section */}
              {summary.stakeholder_nodes.length > 0 && (
                <div>
                  <div className="space-y-1">
                    {summary.stakeholder_nodes.map((node) => (
                      <button
                        key={node.node_id}
                        className="flex items-center gap-2 text-text w-full text-left hover:text-primary-600 transition-colors rounded px-1 -mx-1 py-0.5 hover:bg-primary-50/50"
                        onClick={(e) => {
                          e.stopPropagation();
                          openNodeDetail(node.node_id);
                        }}
                      >
                        <Icon name="FileText" size="xs" className="text-text-secondary shrink-0" />
                        <span className="truncate">{node.node_title}</span>
                        <Badge
                          variant={NODE_TYPE_COLORS[node.node_type as keyof typeof NODE_TYPE_COLORS] || 'gray'}
                        >
                          {nodeLabel(node.node_type)}
                        </Badge>
                        <span className="text-text-secondary shrink-0 ml-auto">
                          {STAKEHOLDER_ROL_LABELS[node.stakeholder_rol] || node.stakeholder_rol}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Org placements section */}
              {placements && placements.length > 0 && (
                <div>
                  <p className="text-text-secondary font-medium mb-1 flex items-center gap-1">
                    <Icon name="Building2" size="xs" />
                    Teams
                  </p>
                  <div className="space-y-1">
                    {placements.map((p) => (
                      <div key={p.id} className="flex items-center gap-2 text-text">
                        <span className="truncate">
                          {p.organisatie_eenheid_naam}
                          {p.functietitel && (
                            <span className="text-text-secondary font-normal">
                              {' '}— {p.functietitel}
                            </span>
                          )}
                        </span>
                        <Badge variant="gray">
                          {DIENSTVERBAND_LABELS[p.dienstverband] || p.dienstverband}
                        </Badge>
                        {showPlacementActions && (
                          <div className="flex items-center gap-1 shrink-0 ml-auto">
                            {!p.eind_datum && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  endPlacement.mutate({
                                    personId: person.id,
                                    placementId: p.id,
                                    data: { eind_datum: todayISO() },
                                  });
                                }}
                                className="text-text-secondary hover:text-amber-600 transition-colors"
                                title="Team-indeling beëindigen"
                              >
                                <Icon name="CheckCircle2" size="xs" />
                              </button>
                            )}
                            {confirmDeleteId === p.id ? (
                              <span className="flex items-center gap-1 text-red-600">
                                <span>Zeker?</span>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    removePlacement.mutate(
                                      { personId: person.id, placementId: p.id },
                                      { onSettled: () => setConfirmDeleteId(null) },
                                    );
                                  }}
                                  className="font-medium hover:underline"
                                >
                                  Ja
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setConfirmDeleteId(null);
                                  }}
                                  className="text-text-secondary hover:text-text"
                                >
                                  Nee
                                </button>
                              </span>
                            ) : (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setConfirmDeleteId(p.id);
                                }}
                                className="text-text-secondary hover:text-red-600 transition-colors"
                                title="Team-indeling verwijderen"
                              >
                                <Icon name="X" size="xs" />
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Samenwerkingsverbanden */}
              {lidmaatschappen && lidmaatschappen.length > 0 && (
                <div>
                  <p className="text-text-secondary font-medium mb-1 flex items-center gap-1">
                    <Icon name="Handshake" size="xs" />
                    Samenwerkingsverbanden
                  </p>
                  <div className="space-y-1">
                    {lidmaatschappen.map((lid) => (
                      <div
                        key={lid.id}
                        className="flex items-center gap-2 text-text"
                      >
                        <Link
                          to={`/samenwerkingsverbanden/${lid.samenwerkingsverband_id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="truncate hover:text-primary-600 transition-colors"
                        >
                          {lid.samenwerkingsverband_naam}
                        </Link>
                        <Badge
                          variant={
                            SAMENWERKINGSVERBAND_TYPE_BADGE_COLORS[
                              lid.samenwerkingsverband_type
                            ] ?? 'gray'
                          }
                        >
                          {SAMENWERKINGSVERBAND_TYPE_LABELS[
                            lid.samenwerkingsverband_type
                          ] ?? lid.samenwerkingsverband_type}
                        </Badge>
                        {lid.rol && (
                          <span className="text-[11px] text-text-secondary shrink-0">
                            — {lid.rol}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* No tasks and no nodes */}
              {summary.open_task_count === 0 && summary.done_task_count === 0 && summary.stakeholder_nodes.length === 0 && (!placements || placements.length === 0) && (!lidmaatschappen || lidmaatschappen.length === 0) && (
                <p className="text-text-secondary">Geen taken, dossiers of teams.</p>
              )}
            </div>
          ) : null}

          {/* Edit button */}
          {onEditPerson && (
            <div
              className="flex justify-end mt-2 pt-2 border-t border-border"
              onClickCapture={(e) => e.stopPropagation()}
            >
              <NlddButton
                text="Bewerken"
                startIcon="pencil"
                variant="neutral-transparent"
                size="sm"
                onClick={() => onEditPerson(person)}
              />
            </div>
          )}
        </div>
      )}

      <SendMessageModal
        open={messageOpen}
        onClose={() => setMessageOpen(false)}
        recipient={person}
      />
    </Card>
  );
}
