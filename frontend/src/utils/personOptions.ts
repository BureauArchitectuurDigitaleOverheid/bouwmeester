import type { Person } from '@/types';
import type { SelectOption } from '@/components/common/CreatableSelect';

/**
 * Build a SelectOption[] from a list of people, with the current person
 * prepended at the top (labelled "(mij)") and deduplicated from the rest.
 *
 * @param people     Full list of people
 * @param currentPerson  The logged-in person (or null)
 * @param mapOption  Optional mapper for each person → SelectOption.
 *                   Defaults to { value: p.id, label: p.naam }.
 */
export function buildPersonOptions(
  people: Person[],
  currentPerson: Person | null,
  mapOption?: (p: Person) => SelectOption,
): SelectOption[] {
  const toOption = mapOption ?? ((p) => ({ value: p.id, label: p.naam }));
  const others = people
    .filter((p) => p.id !== currentPerson?.id)
    .map(toOption);
  if (!currentPerson) return others;
  const selfOption = toOption(currentPerson);
  return [
    { ...selfOption, label: `${selfOption.label} (mij)` },
    ...others,
  ];
}
