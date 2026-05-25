import { FormEvent, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { ImagePlus, KeyRound, Languages, Monitor, Moon, Palette, SaveAll, Settings2, ShieldAlert, Sun, Trash2, UserCog, UserCircle2, UsersRound } from 'lucide-react';
import { api, type User, type UserRole } from '../../lib/api';
import { useAuthStore } from '../../store/auth';
import { useThemeStore, type Theme } from '../../store/theme';

type SystemSetting = { id: string; key: string; value: string; scope: string; is_secret: boolean };

const SECTIONS = [
  { id: 'profile', label: 'Profile', icon: UserCog },
  { id: 'appearance', label: 'Appearance', icon: Palette },
  { id: 'security', label: 'Security', icon: ShieldAlert },
  { id: 'roles', label: 'Roles', icon: UsersRound },
  { id: 'system', label: 'System', icon: Settings2 },
] as const;

type SectionId = (typeof SECTIONS)[number]['id'];

export function SettingsPage() {
  const [section, setSection] = useState<SectionId>('profile');
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Configuration</p>
        <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Settings</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-muted">Manage your profile, appearance, security and global system configuration.</p>
      </div>
      <div className="grid gap-5 lg:grid-cols-[220px_1fr]">
        <nav className="ec-card h-fit p-2">
          {SECTIONS.map((s) => {
            const Icon = s.icon;
            return (
              <button
                key={s.id}
                onClick={() => setSection(s.id)}
                className={
                  'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition ' +
                  (section === s.id ? 'bg-brand-600 text-white' : 'text-ink-muted hover:bg-surface-muted hover:text-ink')
                }
              >
                <Icon size={16} />
                {s.label}
              </button>
            );
          })}
        </nav>
        <div className="space-y-5">
          {section === 'profile' && <ProfilePanel />}
          {section === 'appearance' && <AppearancePanel />}
          {section === 'security' && <SecurityPanel />}
          {section === 'roles' && <RolesPanel />}
          {section === 'system' && <SystemPanel />}
        </div>
      </div>
    </div>
  );
}

function RolesPanel() {
  const queryClient = useQueryClient();
  const { hasRole, user: currentUser } = useAuthStore();
  const canManage = hasRole('Admin');
  const { data, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: async () => (await api.get<User[]>('/users')).data,
    enabled: hasRole('Admin', 'Manager'),
  });

  const updateRole = useMutation({
    mutationFn: async ({ id, role }: { id: string; role: UserRole }) => {
      await api.patch(`/users/${id}`, { role });
    },
    onSuccess: async () => {
      toast.success('Role updated');
      await queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: () => toast.error('Could not update role'),
  });

  const toggleActive = useMutation({
    mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) => {
      await api.patch(`/users/${id}`, { is_active });
    },
    onSuccess: async () => {
      toast.success('User status updated');
      await queryClient.invalidateQueries({ queryKey: ['users'] });
    },
    onError: () => toast.error('Could not update user status'),
  });

  if (!hasRole('Admin', 'Manager')) {
    return (
      <div className="ec-card p-5">
        <div className="flex items-center gap-2">
          <UsersRound size={18} />
          <h2 className="text-lg font-semibold">User roles</h2>
        </div>
        <p className="mt-3 text-sm text-ink-muted">Only Admin and Manager accounts can view the user directory.</p>
      </div>
    );
  }

  return (
    <div className="ec-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2">
          <UsersRound size={18} />
          <h2 className="text-lg font-semibold">User roles</h2>
        </div>
        <span className="ec-badge-blue">Admin, Manager, Employee, Developer + Student, Teacher, Registrar, Dean (Academic)</span>
      </div>
      <table className="ec-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Department</th>
            <th>Role</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            <tr><td colSpan={5}>Loading users...</td></tr>
          ) : data && data.length > 0 ? (
            data.map((u) => (
              <tr key={u.id}>
                <td>{u.full_name}</td>
                <td className="font-mono text-xs">{u.email}</td>
                <td>{u.department || '-'}</td>
                <td>
                  <select
                    className="ec-input max-w-44"
                    value={u.role}
                    disabled={!canManage || updateRole.isPending}
                    onChange={(event) => updateRole.mutate({ id: u.id, role: event.target.value as UserRole })}
                  >
                    <option value="Admin">Admin</option>
                    <option value="Manager">Manager</option>
                    <option value="Employee">Employee</option>
                    <option value="Developer">Developer</option>
                    <option value="Student">Student</option>
                    <option value="Teacher">Teacher</option>
                    <option value="Registrar">Registrar</option>
                    <option value="Dean">Dean</option>
                  </select>
                </td>
                <td>
                  <button
                    className={u.is_active ? 'ec-badge-green' : 'ec-badge-rose'}
                    disabled={!canManage || u.id === currentUser?.id || toggleActive.isPending}
                    onClick={() => toggleActive.mutate({ id: u.id, is_active: !u.is_active })}
                    title={u.id === currentUser?.id ? 'You cannot deactivate yourself here' : 'Toggle active status'}
                  >
                    {u.is_active ? 'Active' : 'Inactive'}
                  </button>
                </td>
              </tr>
            ))
          ) : (
            <tr><td colSpan={5}>No users found.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

const ACCEPTED_AVATAR_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
const MAX_AVATAR_BYTES = 2 * 1024 * 1024;

function AvatarSection() {
  const { user, uploadAvatar, deleteAvatar } = useAuthStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function handlePick(file: File | null | undefined) {
    if (!file) return;
    if (!ACCEPTED_AVATAR_TYPES.includes(file.type)) {
      toast.error('Avatar must be a PNG, JPEG, or WEBP image.');
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      toast.error('Avatar is too large (max 2 MB).');
      return;
    }
    setBusy(true);
    try {
      await uploadAvatar(file);
      toast.success('Avatar updated');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Could not upload avatar');
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function handleRemove() {
    setBusy(true);
    try {
      await deleteAvatar();
      toast.success('Avatar removed');
    } catch {
      toast.error('Could not remove avatar');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-4 rounded-xl border border-border bg-surface p-4">
      <div className="grid h-20 w-20 shrink-0 place-items-center overflow-hidden rounded-full border border-border bg-surface-muted">
        {user?.avatar_url ? (
          <img
            key={user.avatar_url}
            src={user.avatar_url}
            alt={user.full_name}
            className="h-full w-full object-cover"
          />
        ) : (
          <UserCircle2 size={48} className="text-ink-subtle" />
        )}
      </div>
      <div className="flex-1">
        <p className="text-sm font-medium">Profile picture</p>
        <p className="text-xs text-ink-muted">PNG / JPEG / WEBP, up to 2 MB. Stripped of EXIF metadata and downscaled to 512×512.</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            className="ec-btn-secondary"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
          >
            <ImagePlus size={14} /> {user?.avatar_url ? 'Replace' : 'Upload'}
          </button>
          {user?.avatar_url && (
            <button
              type="button"
              className="ec-btn-ghost text-rose-600"
              disabled={busy}
              onClick={handleRemove}
            >
              <Trash2 size={14} /> Remove
            </button>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_AVATAR_TYPES.join(',')}
            className="hidden"
            onChange={(e) => handlePick(e.target.files?.[0])}
          />
        </div>
      </div>
    </div>
  );
}

function ProfilePanel() {
  const { user, updateProfile } = useAuthStore();
  const [full_name, setFullName] = useState(user?.full_name ?? '');
  const [department, setDepartment] = useState(user?.department ?? '');
  const [locale, setLocale] = useState(user?.locale ?? 'en');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setFullName(user?.full_name ?? '');
    setDepartment(user?.department ?? '');
    setLocale(user?.locale ?? 'en');
  }, [user]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await updateProfile({ full_name, department: department || null, locale });
      toast.success('Profile updated');
    } catch {
      toast.error('Could not update profile');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="ec-card space-y-4 p-5">
      <div className="flex items-center gap-2 border-b border-border pb-3">
        <UserCog size={18} />
        <h2 className="text-lg font-semibold">Profile</h2>
      </div>
      <AvatarSection />
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="ec-label" htmlFor="full_name">Full name</label>
          <input id="full_name" className="ec-input" value={full_name} onChange={(e) => setFullName(e.target.value)} required />
        </div>
        <div>
          <label className="ec-label">Email</label>
          <input className="ec-input" value={user?.email ?? ''} disabled />
        </div>
        <div>
          <label className="ec-label" htmlFor="department">Department</label>
          <input id="department" className="ec-input" value={department} onChange={(e) => setDepartment(e.target.value)} />
        </div>
        <div>
          <label className="ec-label" htmlFor="locale"><Languages size={12} className="inline" /> Locale</label>
          <select id="locale" className="ec-input" value={locale} onChange={(e) => setLocale(e.target.value)}>
            <option value="en">English</option>
            <option value="es">Español</option>
            <option value="fr">Français</option>
            <option value="de">Deutsch</option>
          </select>
        </div>
        <div>
          <label className="ec-label">Role</label>
          <input className="ec-input" value={user?.role ?? ''} disabled />
        </div>
        <div>
          <label className="ec-label">Last login</label>
          <input className="ec-input" value={user?.last_login_at ?? '—'} disabled />
        </div>
      </div>
      <div className="flex justify-end">
        <button type="submit" className="ec-btn-primary" disabled={submitting}>
          <SaveAll size={16} /> {submitting ? 'Saving…' : 'Save profile'}
        </button>
      </div>
    </form>
  );
}

function AppearancePanel() {
  const { theme, setTheme } = useThemeStore();
  const options: { value: Theme; label: string; icon: typeof Sun; description: string }[] = [
    { value: 'light', label: 'Light', icon: Sun, description: 'Bright background; best for daylight or projection.' },
    { value: 'dark', label: 'Dark', icon: Moon, description: 'Easy on the eyes for low-light environments.' },
    { value: 'system', label: 'System', icon: Monitor, description: 'Follow your operating system preference.' },
  ];
  return (
    <div className="ec-card space-y-4 p-5">
      <div className="flex items-center gap-2 border-b border-border pb-3">
        <Palette size={18} />
        <h2 className="text-lg font-semibold">Appearance</h2>
      </div>
      <p className="text-sm text-ink-muted">Choose how EnterpriseCore looks.</p>
      <div className="grid gap-3 md:grid-cols-3">
        {options.map((opt) => {
          const Icon = opt.icon;
          const active = theme === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => setTheme(opt.value)}
              className={
                'rounded-xl border p-4 text-left transition ' +
                (active ? 'border-brand-500 bg-brand-600/10 ring-1 ring-brand-500/40' : 'border-border hover:bg-surface-muted')
              }
            >
              <div className="mb-2 flex items-center gap-2">
                <Icon size={18} />
                <p className="font-medium">{opt.label}</p>
              </div>
              <p className="text-xs text-ink-muted">{opt.description}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SecurityPanel() {
  const { changePassword } = useAuthStore();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (next.length < 10) {
      toast.error('Password must be at least 10 characters');
      return;
    }
    if (next !== confirm) {
      toast.error('Passwords do not match');
      return;
    }
    setSubmitting(true);
    try {
      await changePassword(current, next);
      toast.success('Password changed — please sign back in.');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Could not change password');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="ec-card space-y-4 p-5">
      <div className="flex items-center gap-2 border-b border-border pb-3">
        <KeyRound size={18} />
        <h2 className="text-lg font-semibold">Change password</h2>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className="ec-label" htmlFor="current">Current password</label>
          <input
            id="current"
            type="password"
            className="ec-input"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="ec-label" htmlFor="next">New password</label>
          <input
            id="next"
            type="password"
            className="ec-input"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
            minLength={10}
          />
        </div>
        <div>
          <label className="ec-label" htmlFor="confirm">Confirm new password</label>
          <input
            id="confirm"
            type="password"
            className="ec-input"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={10}
          />
        </div>
      </div>
      <p className="text-xs text-ink-muted">Changing your password signs out all of your other sessions.</p>
      <div className="flex justify-end">
        <button type="submit" className="ec-btn-primary" disabled={submitting}>
          <KeyRound size={16} /> {submitting ? 'Updating…' : 'Update password'}
        </button>
      </div>
    </form>
  );
}

function SystemPanel() {
  const queryClient = useQueryClient();
  const { hasRole } = useAuthStore();
  const canEdit = hasRole('Admin', 'Manager');
  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => (await api.get<SystemSetting[]>('/settings')).data,
  });

  const [draft, setDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    if (data) {
      setDraft(Object.fromEntries(data.map((s) => [s.key, s.is_secret ? '' : s.value])));
    }
  }, [data]);

  const secretKeys = new Set((data ?? []).filter((s) => s.is_secret).map((s) => s.key));

  const save = useMutation({
    mutationFn: async (updates: Record<string, string>) => {
      const filtered = Object.fromEntries(Object.entries(updates).filter(([_, v]) => v !== ''));
      const secret_keys = Object.keys(filtered).filter((k) => secretKeys.has(k));
      await api.post('/settings/bulk', { updates: filtered, secret_keys });
    },
    onSuccess: async () => {
      toast.success('Settings saved');
      await queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
    onError: () => toast.error('Could not save settings'),
  });

  return (
    <div className="space-y-4">
      <div className="ec-card overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div className="flex items-center gap-2">
            <Settings2 size={18} />
            <h2 className="text-lg font-semibold">System settings</h2>
          </div>
          {canEdit && (
            <button
              className="ec-btn-primary"
              onClick={() => save.mutate(draft)}
              disabled={save.isPending}
            >
              <SaveAll size={15} /> Save changes
            </button>
          )}
        </div>
        <table className="ec-table">
          <thead>
            <tr>
              <th className="w-1/3">Key</th>
              <th>Value</th>
              <th className="w-24">Scope</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={3}>Loading settings…</td></tr>
            ) : data && data.length > 0 ? (
              data.map((s) => (
                <tr key={s.id}>
                  <td className="font-mono text-xs">{s.key}</td>
                  <td>
                    {s.is_secret ? (
                      <input
                        className="ec-input"
                        type="password"
                        placeholder="(encrypted — set to overwrite)"
                        disabled={!canEdit}
                        value={draft[s.key] ?? ''}
                        onChange={(e) => setDraft((d) => ({ ...d, [s.key]: e.target.value }))}
                      />
                    ) : (
                      <input
                        className="ec-input"
                        disabled={!canEdit}
                        value={draft[s.key] ?? ''}
                        onChange={(e) => setDraft((d) => ({ ...d, [s.key]: e.target.value }))}
                      />
                    )}
                  </td>
                  <td>{s.scope}</td>
                </tr>
              ))
            ) : (
              <tr><td colSpan={3}>No settings configured.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
