import { useCreatePerson, useUpdatePerson, useAddPersonOrganisatie } from '@/hooks/usePeople';
import { todayISO } from '@/utils/dates';
import type { Person, PersonCreateResult, PersonFormSubmitParams } from '@/types';

/**
 * Shared handler for PersonEditForm submissions.
 * Handles all three modes: edit, link-existing, and create(+link).
 */
export function usePersonFormSubmit(
  onDone: () => void,
  onCreated?: (person: PersonCreateResult) => void,
) {
  const createPersonMutation = useCreatePerson();
  const updatePersonMutation = useUpdatePerson();
  const addPlacementMutation = useAddPersonOrganisatie();

  const isPending =
    createPersonMutation.isPending ||
    updatePersonMutation.isPending ||
    addPlacementMutation.isPending;

  const handleSubmit = (params: PersonFormSubmitParams) => {
    switch (params.kind) {
      case 'edit':
        updatePersonMutation.mutate(
          { id: params.personId, data: params.data },
          { onSuccess: onDone },
        );
        break;

      case 'link':
        if (params.orgEenheidId) {
          addPlacementMutation.mutate(
            {
              personId: params.existingPersonId,
              data: {
                organisatie_eenheid_id: params.orgEenheidId,
                dienstverband: params.dienstverband || 'in_dienst',
                start_datum: todayISO(),
              },
            },
            { onSettled: onDone },
          );
        } else {
          onDone();
        }
        break;

      case 'create':
        createPersonMutation.mutate(params.data, {
          onSuccess: (person) => {
            if (params.orgEenheidId) {
              addPlacementMutation.mutate(
                {
                  personId: person.id,
                  data: {
                    organisatie_eenheid_id: params.orgEenheidId,
                    dienstverband: params.dienstverband || 'in_dienst',
                    start_datum: todayISO(),
                  },
                },
                {
                  onSettled: () => {
                    onCreated?.(person);
                    if (!(person.api_key && person.is_agent)) {
                      onDone();
                    }
                  },
                },
              );
            } else {
              onCreated?.(person);
              if (!(person.api_key && person.is_agent)) {
                onDone();
              }
            }
          },
        });
        break;
    }
  };

  return { handleSubmit, isPending };
}
