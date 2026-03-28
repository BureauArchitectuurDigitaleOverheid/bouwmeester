import { useAuth } from '@/contexts/AuthContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/api/client';
import { useCallback, useMemo } from 'react';

interface MyPermissionsResponse {
  roles: unknown[];
  permissions: string[];
}

export function usePermissions() {
  const { person, oidcConfigured } = useAuth();
  const { currentPerson } = useCurrentPerson();

  // In dev mode (no OIDC), fetch permissions for the selected dev person
  const devPersonId = !oidcConfigured ? currentPerson?.id : undefined;

  const { data: devPerms } = useQuery({
    queryKey: ['my-permissions', devPersonId],
    queryFn: () =>
      apiGet<MyPermissionsResponse>(`/api/roles/my-permissions?person_id=${devPersonId}`),
    enabled: !!devPersonId,
  });

  const permissions = useMemo(() => {
    if (!oidcConfigured) {
      return new Set(devPerms?.permissions ?? []);
    }
    return new Set(person?.permissions ?? []);
  }, [person?.permissions, oidcConfigured, devPerms?.permissions]);

  const hasPermission = useCallback((perm: string): boolean => permissions.has(perm), [permissions]);

  const hasAnyPermission = useCallback(
    (...perms: string[]): boolean => perms.some((p) => permissions.has(p)),
    [permissions],
  );

  return { hasPermission, hasAnyPermission, permissions };
}
