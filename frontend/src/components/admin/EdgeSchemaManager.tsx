import { useMemo, useRef, useState } from 'react';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { Icon } from '@/components/nldd/Icon';
import { eventValue, useNlddEvent } from '@/components/nldd/events';
import { useEdgeSchemaRules, useCreateEdgeSchemaRule, useDeleteEdgeSchemaRule } from '@/hooks/useEdgeTypes';
import { useVocabulary } from '@/contexts/VocabularyContext';
import { EDGE_TYPE_VOCABULARY } from '@/vocabulary';
import { NODE_TYPE_LABELS, NodeType } from '@/types';

const SCHEMA_NODE_TYPES = [
  NodeType.DOSSIER,
  NodeType.DOEL,
  NodeType.INSTRUMENT,
  NodeType.BELEIDSKADER,
  NodeType.MAATREGEL,
  NodeType.POLITIEKE_INPUT,
  NodeType.PROBLEEM,
  NodeType.EFFECT,
  NodeType.BELEIDSOPTIE,
  NodeType.BRON,
] as const;

const EDGE_TYPE_IDS = Object.keys(EDGE_TYPE_VOCABULARY);

export function EdgeSchemaManager() {
  const { data: rules, isLoading } = useEdgeSchemaRules();
  const createRule = useCreateEdgeSchemaRule();
  const deleteRule = useDeleteEdgeSchemaRule();
  const { edgeLabel } = useVocabulary();

  const [selectedEdgeType, setSelectedEdgeType] = useState(EDGE_TYPE_IDS[0] ?? '');
  const edgeTypeRef = useRef<HTMLElement>(null);
  useNlddEvent(edgeTypeRef, 'change', (e) => setSelectedEdgeType(eventValue(e)));

  // Build a lookup: `${from}_${to}_${edgeType}` -> rule.id
  const ruleMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const rule of rules ?? []) {
      map.set(`${rule.from_node_type}_${rule.to_node_type}_${rule.edge_type_id}`, rule.id);
    }
    return map;
  }, [rules]);

  const handleToggle = async (fromType: string, toType: string) => {
    const key = `${fromType}_${toType}_${selectedEdgeType}`;
    const existingId = ruleMap.get(key);
    if (existingId) {
      await deleteRule.mutateAsync(existingId);
    } else {
      await createRule.mutateAsync({
        from_node_type: fromType,
        to_node_type: toType,
        edge_type_id: selectedEdgeType,
      });
    }
  };

  if (isLoading) {
    return (
      <nldd-container padding="32">
        <LoadingSpinner />
      </nldd-container>
    );
  }

  const ruleCount = rules?.length ?? 0;

  return (
    <nldd-container gap="16">
      <nldd-text size="sm" color="secondary">
        Beheer welke relatiestypes zijn toegestaan tussen knooppunttypen. Als er geen regels zijn
        gedefinieerd, zijn alle verbindingen toegestaan. Momenteel {ruleCount}{' '}
        {ruleCount === 1 ? 'regel' : 'regels'} actief.
      </nldd-text>

      {/* Edge type selector */}
      <nldd-form-field label="Relatietype">
        <nldd-dropdown ref={edgeTypeRef} width="320px">
          <select value={selectedEdgeType}>
            {EDGE_TYPE_IDS.map((id) => (
              <option key={id} value={id}>
                {edgeLabel(id)}
              </option>
            ))}
          </select>
        </nldd-dropdown>
      </nldd-form-field>

      {/*
        This is a from-type x to-type cross-tab matrix (10x10 toggle cells), not
        a record list, so nldd-table's per-record column model does not fit: the
        first column needs to stay sticky while scrolling, which nldd-table has
        no attribute for. Left as a native <table> per the conversion brief's
        escape hatch ("if a component fights you, you are probably using the
        wrong one"); the interactive cells and card chrome are converted. Cell
        styling here is plain CSS against `--primitives-*` tokens rather than
        Tailwind utilities, since no nldd-* primitive fits a sticky-column matrix.
      */}
      <Card padding={false}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th
                  style={{
                    position: 'sticky',
                    left: 0,
                    zIndex: 1,
                    background: 'var(--primitives-color-neutral-25)',
                    padding: '8px 12px',
                    textAlign: 'left',
                    fontWeight: 500,
                    color: 'var(--primitives-color-neutral-700)',
                    borderBottom: '1px solid var(--primitives-color-neutral-100)',
                    borderRight: '1px solid var(--primitives-color-neutral-100)',
                  }}
                >
                  Van &#x2192; Naar
                </th>
                {SCHEMA_NODE_TYPES.map((nt) => (
                  <th
                    key={nt}
                    style={{
                      padding: '8px',
                      textAlign: 'center',
                      fontWeight: 500,
                      color: 'var(--primitives-color-neutral-700)',
                      borderBottom: '1px solid var(--primitives-color-neutral-100)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {NODE_TYPE_LABELS[nt]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SCHEMA_NODE_TYPES.map((fromType) => (
                <tr key={fromType}>
                  <td
                    style={{
                      position: 'sticky',
                      left: 0,
                      zIndex: 1,
                      background: 'var(--primitives-color-neutral-0)',
                      padding: '8px 12px',
                      fontWeight: 500,
                      color: 'var(--primitives-color-neutral-900)',
                      borderRight: '1px solid var(--primitives-color-neutral-100)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {NODE_TYPE_LABELS[fromType]}
                  </td>
                  {SCHEMA_NODE_TYPES.map((toType) => {
                    const key = `${fromType}_${toType}_${selectedEdgeType}`;
                    const isActive = ruleMap.has(key);
                    return (
                      <td key={toType} style={{ padding: '8px', textAlign: 'center' }}>
                        <button
                          onClick={() => handleToggle(fromType, toType)}
                          disabled={createRule.isPending || deleteRule.isPending}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            height: '28px',
                            width: '28px',
                            borderRadius: '4px',
                            border: 'none',
                            cursor: 'pointer',
                            background: isActive
                              ? 'var(--primitives-color-success-100)'
                              : 'var(--primitives-color-neutral-50)',
                            color: isActive
                              ? 'var(--primitives-color-success-700)'
                              : 'var(--primitives-color-neutral-400)',
                          }}
                          title={
                            isActive
                              ? `${NODE_TYPE_LABELS[fromType]} → ${NODE_TYPE_LABELS[toType]}: ${edgeLabel(selectedEdgeType)} (klik om te verwijderen)`
                              : `${NODE_TYPE_LABELS[fromType]} → ${NODE_TYPE_LABELS[toType]}: ${edgeLabel(selectedEdgeType)} (klik om toe te voegen)`
                          }
                        >
                          <Icon name={isActive ? 'check-mark' : 'close'} size={isActive ? 'md' : 'sm'} />
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </nldd-container>
  );
}
