import { useQuery } from '@tanstack/react-query';
import { getValidEdgeTypes, getEdgeSchemaRules, createEdgeSchemaRule, deleteEdgeSchemaRule } from '@/api/edge-types';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { EdgeSchemaRuleCreate } from '@/types';

export function useValidEdgeTypes(fromNodeType?: string, toNodeType?: string) {
  return useQuery({
    queryKey: queryKeys.edgeTypes.valid(fromNodeType, toNodeType),
    queryFn: () => getValidEdgeTypes(fromNodeType, toNodeType),
    enabled: !!fromNodeType || !!toNodeType,
  });
}

export function useEdgeSchemaRules() {
  return useQuery({
    queryKey: queryKeys.edgeSchemaRules.all,
    queryFn: () => getEdgeSchemaRules(),
  });
}

export function useCreateEdgeSchemaRule() {
  return useMutationWithError({
    mutationFn: (data: EdgeSchemaRuleCreate) => createEdgeSchemaRule(data),
    errorMessage: 'Fout bij aanmaken schemaregel',
    invalidateKeys: [queryKeys.edgeSchemaRules.all, queryKeys.edgeTypes.all],
  });
}

export function useDeleteEdgeSchemaRule() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteEdgeSchemaRule(id),
    errorMessage: 'Fout bij verwijderen schemaregel',
    invalidateKeys: [queryKeys.edgeSchemaRules.all, queryKeys.edgeTypes.all],
  });
}
