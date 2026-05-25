import { api } from './api';

export type PermissionOut = { key: string; category: string; description: string };

export type BuiltInRoleOut = {
  id: string;
  name: string;
  description: string | null;
  is_builtin: true;
  permission_keys: string[];
};

export type CustomRoleOut = {
  id: string;
  name: string;
  description: string | null;
  is_builtin: boolean;
  permission_keys: string[];
  created_at: string;
  updated_at: string;
};

export type CustomRoleIn = {
  name: string;
  description?: string | null;
  permission_keys: string[];
};

export type CustomRoleUpdate = Partial<CustomRoleIn>;

export type RolesPayload = {
  built_in: BuiltInRoleOut[];
  custom: CustomRoleOut[];
};

export type RoleAssignmentOut = {
  id: string;
  user_id: string;
  custom_role_id: string;
  created_at: string;
};

export type EffectivePermissionsOut = {
  user_id: string;
  built_in_role: string;
  custom_role_ids: string[];
  permission_keys: string[];
};

const PREFIX = '/rbac';

export const rbacApi = {
  permissions: () => api.get<PermissionOut[]>(`${PREFIX}/permissions`).then((r) => r.data),
  roles: () => api.get<RolesPayload>(`${PREFIX}/roles`).then((r) => r.data),
  createRole: (body: CustomRoleIn) =>
    api.post<CustomRoleOut>(`${PREFIX}/roles`, body).then((r) => r.data),
  updateRole: (id: string, body: CustomRoleUpdate) =>
    api.patch<CustomRoleOut>(`${PREFIX}/roles/${id}`, body).then((r) => r.data),
  deleteRole: (id: string) => api.delete(`${PREFIX}/roles/${id}`).then(() => true),
  assignRole: (userId: string, customRoleId: string) =>
    api
      .post<RoleAssignmentOut>(`${PREFIX}/users/${userId}/roles`, { custom_role_id: customRoleId })
      .then((r) => r.data),
  revokeRole: (userId: string, roleId: string) =>
    api.delete(`${PREFIX}/users/${userId}/roles/${roleId}`).then(() => true),
  effective: (userId: string) =>
    api.get<EffectivePermissionsOut>(`${PREFIX}/users/${userId}/effective-permissions`).then((r) => r.data),
};

/** Group a flat permission list by category — used by the role editor UI. */
export function groupPermissions(perms: PermissionOut[]): Record<string, PermissionOut[]> {
  const out: Record<string, PermissionOut[]> = {};
  for (const p of perms) {
    if (!out[p.category]) out[p.category] = [];
    out[p.category].push(p);
  }
  return out;
}
