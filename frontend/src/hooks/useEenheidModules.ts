import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getEenheidModules,
  updateEenheidModule,
  getAvailableModules,
} from '@/api/eenheidModules';

export function useEenheidModules(eenheidId: string | undefined) {
  return useQuery({
    queryKey: ['eenheid-modules', eenheidId],
    queryFn: () => getEenheidModules(eenheidId!),
    enabled: !!eenheidId,
  });
}

export function useAvailableModules() {
  return useQuery({
    queryKey: ['available-modules'],
    queryFn: getAvailableModules,
  });
}

export function useUpdateEenheidModule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      eenheidId,
      module,
      enabled,
    }: {
      eenheidId: string;
      module: string;
      enabled: boolean;
    }) => updateEenheidModule(eenheidId, module, enabled),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({
        queryKey: ['eenheid-modules', variables.eenheidId],
      });
    },
  });
}
