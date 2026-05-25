import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Plus, RefreshCw, Send, Users, X } from 'lucide-react';
import {
  academicApi,
  academicDeepApi,
  type StudyMatchPreview,
  type StudyProfileInput,
} from '../../lib/academic';

const EMPTY: StudyProfileInput = {
  bio: '',
  subjects: [],
  availability: '',
  preferred_style: '',
};

export function AcademicStudyBuddiesPage() {
  const qc = useQueryClient();
  const profilesQ = useQuery({
    queryKey: ['academic', 'study-profiles'],
    queryFn: () => academicApi.listStudyProfiles(),
  });
  const matchesQ = useQuery({
    queryKey: ['academic', 'study-matches'],
    queryFn: () => academicApi.listMatches(),
  });
  const [editing, setEditing] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Study Buddies</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Find classmates studying the same subjects on the same schedule.
          </p>
        </div>
        <button
          type="button"
          className="ec-btn-primary"
          onClick={() => setEditing(true)}
        >
          <Plus size={14} /> Update my profile
        </button>
      </div>

      <TopMatchesPanel />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section>
          <p className="text-sm font-semibold mb-2">Top matches for you</p>
          {matchesQ.isLoading && (
            <p className="text-sm text-ink-muted">Loading…</p>
          )}
          {matchesQ.data && matchesQ.data.length === 0 && (
            <p className="ec-card p-6 text-center text-sm text-ink-muted">
              No matches yet — fill out your profile to seed the matcher.
            </p>
          )}
          <div className="space-y-2">
            {(matchesQ.data ?? []).map((m) => (
              <div
                key={m.user_id}
                className="ec-card flex items-start gap-3 p-3"
              >
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600/10 text-brand-600">
                  <Users size={16} />
                </span>
                <div className="flex-1 min-w-0">
                  <p className="font-medium">{m.name}</p>
                  {m.bio && (
                    <p className="line-clamp-2 text-xs text-ink-muted">
                      {m.bio}
                    </p>
                  )}
                  {m.shared_subjects.length > 0 && (
                    <p className="mt-1 text-xs text-ink-muted">
                      Shared: {m.shared_subjects.join(', ')}
                    </p>
                  )}
                </div>
                <span className="ec-badge-green">{Math.round(m.score)}%</span>
              </div>
            ))}
          </div>
        </section>
        <section>
          <p className="text-sm font-semibold mb-2">All profiles</p>
          {profilesQ.isLoading && (
            <p className="text-sm text-ink-muted">Loading…</p>
          )}
          {profilesQ.data && profilesQ.data.length === 0 && (
            <p className="ec-card p-6 text-center text-sm text-ink-muted">
              No public profiles yet.
            </p>
          )}
          <ul className="space-y-2">
            {(profilesQ.data ?? []).map((p) => (
              <li key={p.id} className="ec-card p-3 text-sm">
                {p.bio && <p className="text-ink-muted">{p.bio}</p>}
                {p.subjects.length > 0 && (
                  <p className="mt-1 text-xs">
                    Subjects: {p.subjects.join(', ')}
                  </p>
                )}
                {p.availability && (
                  <p className="text-xs text-ink-muted">
                    Available: {p.availability}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>

      {editing && (
        <ProfileModal
          onClose={() => setEditing(false)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ['academic', 'study-profiles'] });
            qc.invalidateQueries({ queryKey: ['academic', 'study-matches'] });
          }}
        />
      )}
    </div>
  );
}

function ProfileModal({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<StudyProfileInput>(EMPTY);
  const [subjectInput, setSubjectInput] = useState('');
  const save = useMutation({
    mutationFn: () => academicApi.upsertStudyProfile(form),
    onSuccess: () => {
      onSaved();
      toast.success('Profile saved');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to save');
    },
  });

  function addSubject() {
    const v = subjectInput.trim();
    if (!v) return;
    setForm({ ...form, subjects: Array.from(new Set([...form.subjects, v])) });
    setSubjectInput('');
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">Study buddy profile</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <form
          className="space-y-3 p-5"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div>
            <label className="ec-label">Bio</label>
            <textarea
              className="ec-input min-h-[80px]"
              value={form.bio ?? ''}
              onChange={(e) => setForm({ ...form, bio: e.target.value })}
            />
          </div>
          <div>
            <label className="ec-label">Subjects</label>
            <div className="flex gap-2">
              <input
                className="ec-input flex-1"
                value={subjectInput}
                onChange={(e) => setSubjectInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    addSubject();
                  }
                }}
                placeholder="e.g. Calculus"
              />
              <button
                type="button"
                className="ec-btn-secondary"
                onClick={addSubject}
              >
                Add
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {form.subjects.map((s) => (
                <button
                  type="button"
                  key={s}
                  className="ec-badge bg-surface-muted text-ink-muted"
                  onClick={() =>
                    setForm({
                      ...form,
                      subjects: form.subjects.filter((x) => x !== s),
                    })
                  }
                >
                  {s} ×
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="ec-label">Availability</label>
            <input
              className="ec-input"
              placeholder="weekday evenings"
              value={form.availability ?? ''}
              onChange={(e) =>
                setForm({ ...form, availability: e.target.value })
              }
            />
          </div>
          <div>
            <label className="ec-label">Preferred study style</label>
            <input
              className="ec-input"
              placeholder="silent group, problem-solving, etc"
              value={form.preferred_style ?? ''}
              onChange={(e) =>
                setForm({ ...form, preferred_style: e.target.value })
              }
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="ec-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="ec-btn-primary"
              disabled={save.isPending}
            >
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function TopMatchesPanel() {
  const qc = useQueryClient();
  const topQ = useQuery({
    queryKey: ['academic', 'study-match', 'top'],
    queryFn: () => academicDeepApi.topStudyMatches(10),
  });
  const refresh = useMutation({
    mutationFn: () => academicDeepApi.refreshStudyMatches(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'study-match', 'top'] });
      toast.success('Matches refreshed');
    },
    onError: () => toast.error('No profile yet — set one up first.'),
  });
  const connect = useMutation({
    mutationFn: (matchId: string) => academicDeepApi.connectMatch(matchId),
    onSuccess: () => toast.success('Request sent'),
    onError: () => toast.error('Connect failed'),
  });
  const data = (topQ.data ?? []) as StudyMatchPreview[];
  return (
    <section className="ec-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="font-semibold inline-flex items-center gap-2">
          <Users size={14} className="text-brand-600" />
          Top matches (refreshed live)
        </p>
        <button
          type="button"
          className="ec-btn-secondary"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
        >
          <RefreshCw size={12} /> {refresh.isPending ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
      {data.length === 0 ? (
        <p className="text-sm text-ink-muted">
          No matches yet. Create or update your profile, then refresh.
        </p>
      ) : (
        <ul className="divide-y divide-border/60">
          {data.map((m) => (
            <li
              key={m.match_id}
              className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate font-medium">{m.full_name}</p>
                <p className="text-xs text-ink-muted">
                  {m.department || 'No dept'} · {m.semester || '—'}
                  {m.shared_courses.length > 0 && (
                    <> · shared: {m.shared_courses.join(', ')}</>
                  )}
                </p>
              </div>
              <span className="ec-badge-green">{m.score}</span>
              <button
                type="button"
                className="ec-btn-ghost !px-2 !py-1 text-xs"
                onClick={() => connect.mutate(m.match_id)}
                disabled={connect.isPending}
              >
                <Send size={11} /> Connect
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
