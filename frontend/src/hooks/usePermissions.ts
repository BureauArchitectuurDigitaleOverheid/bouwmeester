import { useAuth } from '@/contexts/AuthContext';
import { useCallback, useMemo } from 'react';

export function usePermissions() {
  const { person } = useAuth();

  const permissions = useMemo(() => new Set(person?.permissions ?? []), [person?.permissions]);

  const hasPermission = useCallback((perm: string): boolean => permissions.has(perm), [permissions]);

  const hasAnyPermission = useCallback(
    (...perms: string[]): boolean => perms.some((p) => permissions.has(p)),
    [permissions],
  );

  return { hasPermission, hasAnyPermission, permissions };
}
