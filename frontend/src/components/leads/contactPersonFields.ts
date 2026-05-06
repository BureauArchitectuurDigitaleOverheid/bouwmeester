/**
 * Type + helper voor de NewContactPersonFields-component.
 * In aparte file gehouden zodat NewContactPersonFields.tsx alleen
 * componenten exporteert (vereist voor React Fast Refresh).
 */

export interface ContactPersonFieldsState {
  naam: string;
  email: string;
  phone: string;
  functie: string;
  expertise: string;
  organisatieEenheidId: string;
  samenwerkingsverbandIds: Set<string>;
}

export const emptyContactPersonFields = (): ContactPersonFieldsState => ({
  naam: '',
  email: '',
  phone: '',
  functie: '',
  expertise: '',
  organisatieEenheidId: '',
  samenwerkingsverbandIds: new Set(),
});
