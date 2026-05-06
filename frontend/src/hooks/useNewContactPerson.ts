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

export function useCreateContactPerson() {
  const createPerson = useCreatePerson();
  const addPersonPhone = useAddPersonPhone();
  const addPersonOrg = useAddPersonOrganisatie();
  const addLid = useAddLid();

  const create = useCallback(
    async (input: NewContactPersonInput): Promise<{ personId: string } | null> => {
      const naam = input.naam.trim();
      if (!naam) return null;

      const email = input.email?.trim() || undefined;
      const phone = input.phone?.trim() || undefined;

      // 1. Maak de persoon. Foutgevallen blokkeren de hele flow; toast wordt
      //    door useMutationWithError getoond.
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

      // 2. Best-effort: extra velden die niet via createPerson gaan
      //    (telefoon staat als secundair record). Falen geeft een toast en
      //    blokkeert de lead-koppeling niet — de persoon bestaat al, beter
      //    gekoppeld zonder telefoon dan helemaal niks.
      if (phone) {
        try {
          await addPersonPhone.mutateAsync({
            personId,
            data: { phone_number: phone, label: 'werk', is_default: true },
          });
        } catch {
          /* toast uit useMutationWithError */
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
          /* toast */
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
          /* toast */
        }
      }

      return { personId };
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
