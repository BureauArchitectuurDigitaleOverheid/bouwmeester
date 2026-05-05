import { apiGet } from './client';
import type { PublicInitiatief } from '@/types';

export async function getPublicInitiatief(slug: string): Promise<PublicInitiatief> {
  return apiGet<PublicInitiatief>(
    `/api/public/initiatieven/by-slug/${encodeURIComponent(slug)}`,
  );
}
