import { useAuth } from '@/contexts/AuthContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/api/client';
import { useCallback, useMemo } from 'react';

interface MyPermissionsResponse {
  roles: unknown[];
  permissions: string[];
  system_permissions?: string[];
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

  // System-level permissions from the backend (apply to all eenheden)
  const systemPermissions = useMemo(() => {
    const raw = !oidcConfigured
      ? devPerms?.system_permissions ?? []
      : person?.system_permissions ?? [];
    return new Set(raw);
  }, [person?.system_permissions, oidcConfigured, devPerms?.system_permissions]);

  const hasPermission = useCallback((perm: string): boolean => permissions.has(perm), [permissions]);

  const hasAnyPermission = useCallback(
    (...perms: string[]): boolean => perms.some((p) => permissions.has(p)),
    [permissions],
  );

  // Dev mode (no OIDC) has no user and the backend allows everything.
  const isSuperAdmin = !oidcConfigured || (person?.is_admin ?? false);

  // Eenheden whose members this person manages, with the same inheritance
  // the backend applies (the eenheid itself or anything above it).
  const managedSubtree = useMemo(
    () => new Set(person?.managed_subtree_ids ?? []),
    [person?.managed_subtree_ids],
  );
  const managesEenheid = useCallback(
    (eenheidId: string): boolean =>
      isSuperAdmin || managedSubtree.has('*') || managedSubtree.has(eenheidId),
    [isSuperAdmin, managedSubtree],
  );

  // Tenant-wide actions (syncs, merges, restoring a backup) need the
  // permission from a system role, not from a role scoped to one eenheid.
  const hasSystemPermission = useCallback(
    (perm: string): boolean => isSuperAdmin || systemPermissions.has(perm),
    [isSuperAdmin, systemPermissions],
  );

  return {
    hasPermission,
    hasAnyPermission,
    hasSystemPermission,
    managesEenheid,
    isSuperAdmin,
    permissions,
  };
}
