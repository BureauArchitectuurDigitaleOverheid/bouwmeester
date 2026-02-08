import { useMemo } from 'react';
import type { SelectOption } from '@/components/common/CreatableSelect';

/**
 * Convert an enum + labels map into memoized SelectOption[].
 */
export function useEnumOptions<T extends string>(
  enumObj: Record<string, T>,
  labels: Record<T, string>,
): SelectOption[] {
  return useMemo(
    () =>
      Object.values(enumObj).map((value) => ({
        value,
        label: labels[value],
      })),
    [enumObj, labels],
  );
}
