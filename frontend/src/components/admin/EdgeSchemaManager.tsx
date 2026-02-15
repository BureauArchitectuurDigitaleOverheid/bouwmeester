import { useMemo, useState } from 'react';
import { Check, X } from 'lucide-react';
import { Card } from '@/components/common/Card';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
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
    return <LoadingSpinner className="py-8" />;
  }

  const ruleCount = rules?.length ?? 0;

  return (
    <div className="space-y-4">
      <p className="text-sm text-text-secondary">
        Beheer welke relatiestypes zijn toegestaan tussen knooppunttypen. Als er geen regels zijn gedefinieerd, zijn alle verbindingen toegestaan.
        Momenteel {ruleCount} {ruleCount === 1 ? 'regel' : 'regels'} actief.
      </p>

      {/* Edge type selector */}
      <div>
        <label className="block text-sm font-medium text-text mb-1">Relatietype</label>
        <select
          value={selectedEdgeType}
          onChange={(e) => setSelectedEdgeType(e.target.value)}
          className="w-full max-w-xs rounded-lg border border-border bg-white px-3 py-2 text-sm text-text focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
        >
          {EDGE_TYPE_IDS.map((id) => (
            <option key={id} value={id}>
              {edgeLabel(id)}
            </option>
          ))}
        </select>
      </div>

      {/* Matrix */}
      <Card padding={false}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-gray-50 px-3 py-2 text-left font-medium text-text-secondary border-b border-r border-border">
                  Van &#x2192; Naar
                </th>
                {SCHEMA_NODE_TYPES.map((nt) => (
                  <th
                    key={nt}
                    className="px-2 py-2 text-center font-medium text-text-secondary border-b border-border whitespace-nowrap"
                  >
                    {NODE_TYPE_LABELS[nt]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SCHEMA_NODE_TYPES.map((fromType) => (
                <tr key={fromType} className="hover:bg-gray-50/50">
                  <td className="sticky left-0 z-10 bg-white px-3 py-2 font-medium text-text border-r border-border whitespace-nowrap">
                    {NODE_TYPE_LABELS[fromType]}
                  </td>
                  {SCHEMA_NODE_TYPES.map((toType) => {
                    const key = `${fromType}_${toType}_${selectedEdgeType}`;
                    const isActive = ruleMap.has(key);
                    return (
                      <td key={toType} className="px-2 py-2 text-center">
                        <button
                          onClick={() => handleToggle(fromType, toType)}
                          disabled={createRule.isPending || deleteRule.isPending}
                          className={`inline-flex items-center justify-center h-7 w-7 rounded transition-colors ${
                            isActive
                              ? 'bg-green-100 text-green-700 hover:bg-green-200'
                              : 'bg-gray-100 text-gray-400 hover:bg-gray-200'
                          }`}
                          title={
                            isActive
                              ? `${NODE_TYPE_LABELS[fromType]} → ${NODE_TYPE_LABELS[toType]}: ${edgeLabel(selectedEdgeType)} (klik om te verwijderen)`
                              : `${NODE_TYPE_LABELS[fromType]} → ${NODE_TYPE_LABELS[toType]}: ${edgeLabel(selectedEdgeType)} (klik om toe te voegen)`
                          }
                        >
                          {isActive ? <Check className="h-4 w-4" /> : <X className="h-3.5 w-3.5" />}
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
    </div>
  );
}
