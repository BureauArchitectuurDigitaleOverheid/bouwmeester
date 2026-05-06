/**
 * Helper-hook die een externe contactpersoon aanmaakt met optionele
 * follow-ups (organisatie-plaatsing, samenwerkingsverband-lidmaatschappen,
 * extra telefoonnummer).
 *
 * Gebruik vanuit AddLeadContactModal, LeadDetailPanel en LeadIntakeDialog
 * zodat alle drie de flows dezelfde set velden ondersteunen.
 */

import { useCallback } from 'react';
import {
  useAddPersonOrganisatie,
  useAddPersonPhone,
  useCreatePerson,
} from '@/hooks/usePeople';
import { useAddLid } from '@/hooks/useSamenwerkingsverbanden';

export interface NewContactPersonInput {
  naam: string;
  email?: string;
  /** Optioneel telefoonnummer; opgeslagen als 'werk'-label. */
  phone?: string;
  functie?: string;
  expertise?: string;
  organisatieEenheidId?: string;
  samenwerkingsverbandIds?: string[];
}

export interface CreateContactPersonResult {
  personId: string;
  /** Velden die niet konden worden opgeslagen (best-effort). */
  followUpFailures: Array<'phone' | 'plaatsing' | 'samenwerkingsverband'>;
}

export function useCreateContactPerson() {
  const createPerson = useCreatePerson();
  const addPersonPhone = useAddPersonPhone();
  const addPersonOrg = useAddPersonOrganisatie();
  const addLid = useAddLid();

  const create = useCallback(
    async (input: NewContactPersonInput): Promise<CreateContactPersonResult | null> => {
      const naam = input.naam.trim();
      if (!naam) return null;

      const email = input.email?.trim() || undefined;
      const phone = input.phone?.trim() || undefined;

      // 1. Maak de persoon. Foutgevallen blokkeren de hele flow.
      let personId: string;
      try {
        const person = await createPerson.mutateAsync({
          naam,
          email,
          functie: input.functie?.trim() || undefined,
          expertise: input.expertise?.trim() || undefined,
          force: true,
        });
        personId = person.id;
      } catch {
        return null;
      }

      const failures: CreateContactPersonResult['followUpFailures'] = [];

      // 2. Best-effort: extra velden die niet via createPerson gaan
      //    (telefoon staat alleen als secundair record op een persoon).
      if (phone) {
        try {
          await addPersonPhone.mutateAsync({
            personId,
            data: { phone_number: phone, label: 'werk', is_default: true },
          });
        } catch {
          failures.push('phone');
        }
      }

      // 3. Org-plaatsing
      if (input.organisatieEenheidId) {
        try {
          await addPersonOrg.mutateAsync({
            personId,
            data: {
              organisatie_eenheid_id: input.organisatieEenheidId,
              start_datum: new Date().toISOString().slice(0, 10),
            },
          });
        } catch {
          failures.push('plaatsing');
        }
      }

      // 4. Samenwerkingsverband-lidmaatschappen
      const today = new Date().toISOString().slice(0, 10);
      for (const swvId of input.samenwerkingsverbandIds ?? []) {
        try {
          await addLid.mutateAsync({
            swvId,
            data: { person_id: personId, start_datum: today },
          });
        } catch {
          failures.push('samenwerkingsverband');
        }
      }

      return { personId, followUpFailures: failures };
    },
    [createPerson, addPersonPhone, addPersonOrg, addLid],
  );

  return {
    create,
    isPending:
      createPerson.isPending ||
      addPersonPhone.isPending ||
      addPersonOrg.isPending ||
      addLid.isPending,
  };
}
