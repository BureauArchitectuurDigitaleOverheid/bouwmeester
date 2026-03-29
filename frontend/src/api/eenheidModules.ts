import { apiGet, apiPut } from './client';

export interface EenheidModuleConfig {
  module: string;
  enabled: boolean;
  inherited_from: string | null;
  inherited_from_naam: string | null;
}

export interface EenheidModulesResponse {
  eenheid_id: string;
  modules: EenheidModuleConfig[];
}

export async function getEenheidModules(
  eenheidId: string,
): Promise<EenheidModulesResponse> {
  return apiGet<EenheidModulesResponse>(`/api/eenheid-modules/${eenheidId}`);
}

export async function updateEenheidModule(
  eenheidId: string,
  module: string,
  enabled: boolean,
): Promise<EenheidModulesResponse> {
  return apiPut<EenheidModulesResponse>(`/api/eenheid-modules/${eenheidId}`, {
    module,
    enabled,
  });
}

export async function getAvailableModules(): Promise<Record<string, string>> {
  return apiGet<Record<string, string>>('/api/eenheid-modules');
}
