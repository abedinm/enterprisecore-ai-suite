import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Pencil, Plus, Trash2, UserCog, X } from 'lucide-react';
import { groupPermissions, rbacApi, type CustomRoleOut } from '../../lib/rbac';
import { useAuthStore } from '../../store/auth';
import { PermissionDenied } from './OrgLayout';

export function RolesTab() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole('Admin'));

  const rolesQ = useQuery({ queryKey: ['rbac', 'roles'], queryFn: () => rbacApi.roles(), enabled: isAdmin });
  const permsQ = useQuery({
    queryKey: ['rbac', 'permissions'],
    queryFn: () => rbacApi.permissions(),
    enabled: isAdmin,
  });

  const [editing, setEditing] = useState<CustomRoleOut | 'new' | null>(null);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editKeys, setEditKeys] = useState<string[]>([]);

  function openEdit(role: CustomRoleOut | 'new') {
    setEditing(role);
    if (role === 'new') {
      setEditName('');
      setEditDesc('');
      setEditKeys([]);
    } else {
      setEditName(role.name);
      setEditDesc(role.description ?? '');
      setEditKeys(role.permission_keys);
    }
  }

  const grouped = useMemo(() => (permsQ.data ? groupPermissions(permsQ.data) : {}), [permsQ.data]);

  const save = useMutation({
    mutationFn: async () => {
      const body = { name: editName, description: editDesc, permission_keys: editKeys };
      if (editing === 'new') return rbacApi.createRole(body);
      if (editing && typeof editing === 'object') return rbacApi.updateRole(editing.id, body);
      throw new Error('No role to save');
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rbac', 'roles'] });
      setEditing(null);
      toast.success('Role saved');
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail ?? 'Could not save role'),
  });

  const del = useMutation({
    mutationFn: (id: string) => rbacApi.deleteRole(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rbac', 'roles'] });
      setEditing(null);
      toast.success('Role deleted');
    },
  });

  if (!isAdmin) return <PermissionDenied what="manage roles" />;
  if (rolesQ.isLoading) return <p className="text-sm text-ink-muted">Loading roles…</p>;

  return (
    <div className="space-y-4">
      <div className="ec-card p-5">
        <h2 className="text-lg font-semibold flex items-center gap-2"><UserCog size={18} /> Built-in roles</h2>
        <p className="text-sm text-ink-muted">Read-only. Permissions are baked into the suite.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {rolesQ.data?.built_in.map((r) => (
            <div key={r.id} className="rounded-lg border border-border bg-surface-muted/30 p-3">
              <p className="font-semibold">{r.name}</p>
              <p className="mt-1 text-xs text-ink-subtle">{r.permission_keys.length} permissions</p>
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer text-brand-600 hover:underline">View permissions</summary>
                <ul className="mt-2 max-h-40 overflow-y-auto space-y-0.5 font-mono text-[11px]">
                  {r.permission_keys.map((k) => (
                    <li key={k}>{k}</li>
                  ))}
                </ul>
              </details>
            </div>
          ))}
        </div>
      </div>

      <div className="ec-card p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Custom roles</h2>
            <p className="text-sm text-ink-muted">Define tenant-scoped roles with their own permissions.</p>
          </div>
          <button className="ec-btn-primary" onClick={() => openEdit('new')} data-testid="role-new">
            <Plus size={16} /> New role
          </button>
        </div>

        {(rolesQ.data?.custom.length ?? 0) === 0 ? (
          <p className="mt-4 py-4 text-center text-sm text-ink-muted">No custom roles yet.</p>
        ) : (
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-ink-subtle">
                <th className="py-2 pr-3">Name</th>
                <th className="py-2 pr-3">Description</th>
                <th className="py-2 pr-3">Permissions</th>
                <th className="py-2 pr-3" />
              </tr>
            </thead>
            <tbody>
              {rolesQ.data!.custom.map((r) => (
                <tr key={r.id} className="border-b border-border/40">
                  <td className="py-2 pr-3 font-medium">{r.name}</td>
                  <td className="py-2 pr-3 text-ink-muted">{r.description ?? '—'}</td>
                  <td className="py-2 pr-3 text-ink-muted">{r.permission_keys.length}</td>
                  <td className="py-2 pr-3 text-right">
                    <button
                      className="rounded p-1.5 text-brand-600 hover:bg-brand-600/10"
                      onClick={() => openEdit(r)}
                      title="Edit"
                    >
                      <Pencil size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editing !== null ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 backdrop-blur-sm p-4">
          <div className="ec-card w-full max-w-2xl p-5 relative">
            <button
              className="absolute right-2 top-2 rounded-md p-1.5 text-ink-muted hover:bg-surface-muted"
              onClick={() => setEditing(null)}
              aria-label="Close"
            >
              <X size={16} />
            </button>
            <h3 className="text-lg font-semibold">{editing === 'new' ? 'New custom role' : `Edit ${editing.name}`}</h3>
            <div className="mt-4 space-y-3">
              <div>
                <label className="ec-label" htmlFor="role-name">Name</label>
                <input
                  id="role-name"
                  className="ec-input"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  data-testid="role-name"
                />
              </div>
              <div>
                <label className="ec-label" htmlFor="role-desc">Description</label>
                <input
                  id="role-desc"
                  className="ec-input"
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                />
              </div>
              <div>
                <label className="ec-label">Permissions</label>
                <div className="max-h-72 overflow-y-auto space-y-3 rounded-lg border border-border p-3">
                  {Object.entries(grouped).map(([category, perms]) => (
                    <div key={category}>
                      <p className="text-xs font-semibold uppercase tracking-wider text-ink-subtle">{category}</p>
                      <div className="mt-1 grid gap-1 sm:grid-cols-2">
                        {perms.map((p) => (
                          <label key={p.key} className="flex items-center gap-2 text-xs">
                            <input
                              type="checkbox"
                              checked={editKeys.includes(p.key)}
                              onChange={(e) => {
                                setEditKeys((ks) =>
                                  e.target.checked ? [...ks, p.key] : ks.filter((k) => k !== p.key),
                                );
                              }}
                            />
                            <span className="truncate" title={p.description}>{p.key}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-4 flex justify-between">
              {typeof editing === 'object' ? (
                <button
                  className="ec-btn-secondary text-rose-600"
                  onClick={() => del.mutate(editing.id)}
                  disabled={del.isPending}
                >
                  <Trash2 size={16} /> Delete
                </button>
              ) : <div />}
              <div className="flex gap-2">
                <button className="ec-btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
                <button
                  className="ec-btn-primary"
                  onClick={() => save.mutate()}
                  disabled={save.isPending || !editName}
                  data-testid="role-save"
                >
                  {save.isPending ? 'Saving…' : 'Save role'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
