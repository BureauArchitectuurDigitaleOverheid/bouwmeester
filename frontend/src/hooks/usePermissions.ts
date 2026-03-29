import { useAuth } from '@/contexts/AuthContext';
import { useCurrentPerson } from '@/contexts/CurrentPersonContext';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/api/client';
import { useCallback, useMemo } from 'react';

interface MyPermissionsResponse {
  roles: unknown[];
  permissions: string[];
  scoped_permissions?: Record<string, string[]>;
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

  // Build per-eenheid permission lookup
  const scopedPermissions = useMemo(() => {
    const raw = !oidcConfigured
      ? devPerms?.scoped_permissions ?? {}
      : person?.scoped_permissions ?? {};
    const map = new Map<string, Set<string>>();
    for (const [eenheidId, perms] of Object.entries(raw)) {
      map.set(eenheidId, new Set(perms));
    }
    return map;
  }, [person?.scoped_permissions, oidcConfigured, devPerms?.scoped_permissions]);

  // Derive system-level permissions: those in the flat set but not in any
  // scoped set. These apply to all eenheden.
  const systemPermissions = useMemo(() => {
    const allScoped = new Set<string>();
    for (const perms of scopedPermissions.values()) {
      for (const p of perms) allScoped.add(p);
    }
    const sys = new Set<string>();
    for (const p of permissions) {
      if (!allScoped.has(p)) sys.add(p);
    }
    return sys;
  }, [permissions, scopedPermissions]);

  const hasPermission = useCallback((perm: string): boolean => permissions.has(perm), [permissions]);

  const hasAnyPermission = useCallback(
    (...perms: string[]): boolean => perms.some((p) => permissions.has(p)),
    [permissions],
  );

  const isAdmin = person?.is_admin ?? false;

  const hasPermissionForEenheid = useCallback(
    (perm: string, eenheidId: string): boolean => {
      if (isAdmin) return true;
      // System-level permissions apply everywhere
      if (systemPermissions.has(perm)) return true;
      // Check scoped permissions for this specific eenheid
      const eenheidPerms = scopedPermissions.get(eenheidId);
      return eenheidPerms?.has(perm) ?? false;
    },
    [isAdmin, systemPermissions, scopedPermissions],
  );

  return { hasPermission, hasAnyPermission, hasPermissionForEenheid, permissions, scopedPermissions };
}
