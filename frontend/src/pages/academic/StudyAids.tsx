import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { History, Lightbulb, PlayCircle, Plus, RefreshCw, Sparkles, Trash2, X } from 'lucide-react';
import {
  academicApi,
  academicDeepApi,
  type GeneratedAids,
  type StudyNoteInput,
  type StudyQuiz,
} from '../../lib/academic';
import { formatDateTime } from '../../lib/utils';

const EMPTY: StudyNoteInput = {
  title: '',
  body: '',
  subject: '',
};

export function AcademicStudyAidsPage() {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['academic', 'study-notes'],
    queryFn: () => academicApi.listStudyNotes(),
  });
  const [creating, setCreating] = useState(false);
  const [generating, setGenerating] = useState<{
    text: string;
    result: GeneratedAids | null;
  } | null>(null);

  const remove = useMutation({
    mutationFn: (id: string) => academicApi.deleteStudyNote(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'study-notes'] });
      toast.success('Note removed');
    },
  });

  const generate = useMutation({
    mutationFn: (text: string) =>
      academicApi.generateAids({ text, count: 6 }),
    onSuccess: (data) => {
      setGenerating((g) => (g ? { ...g, result: data } : g));
      toast.success('Generated study aids');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to generate');
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Study Aids</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Personal study notes — and an AI flashcard/MCQ generator that turns
            pasted text into review material.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="ec-btn-secondary"
            onClick={() => setGenerating({ text: '', result: null })}
          >
            <Sparkles size={14} /> Generate flashcards
          </button>
          <button
            type="button"
            className="ec-btn-primary"
            onClick={() => setCreating(true)}
          >
            <Plus size={14} /> New note
          </button>
        </div>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}
      {listQ.data && listQ.data.length === 0 && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted">
          No notes yet. Start a note or generate aids from pasted text.
        </p>
      )}
      {listQ.data && listQ.data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {listQ.data.map((n) => (
            <article key={n.id} className="ec-card flex flex-col gap-2 p-4">
              <div className="flex items-start justify-between">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600/10 text-brand-600">
                  <Lightbulb size={16} />
                </span>
                {n.subject && (
                  <span className="ec-badge bg-surface-muted text-ink-muted">
                    {n.subject}
                  </span>
                )}
              </div>
              <p className="font-semibold">{n.title}</p>
              <p className="line-clamp-4 whitespace-pre-line text-xs text-ink-muted">
                {n.body}
              </p>
              <NoteActions noteId={n.id} />
              <div className="mt-auto flex justify-end pt-2">
                <button
                  type="button"
                  className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                  onClick={() => {
                    if (confirm(`Delete "${n.title}"?`)) remove.mutate(n.id);
                  }}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <QuizHistoryPanel />

      {creating && <NoteModal onClose={() => setCreating(false)} />}
      {generating && (
        <GenerateModal
          state={generating}
          onChangeText={(text) =>
            setGenerating((g) => (g ? { ...g, text } : g))
          }
          pending={generate.isPending}
          onGenerate={() => generate.mutate(generating.text)}
          onClose={() => setGenerating(null)}
        />
      )}
    </div>
  );
}

function NoteModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<StudyNoteInput>(EMPTY);
  const save = useMutation({
    mutationFn: () => academicApi.createStudyNote(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'study-notes'] });
      toast.success('Note saved');
      onClose();
    },
  });
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">New study note</p>
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
            <label className="ec-label">Title</label>
            <input
              required
              className="ec-input"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>
          <div>
            <label className="ec-label">Subject</label>
            <input
              className="ec-input"
              value={form.subject ?? ''}
              onChange={(e) => setForm({ ...form, subject: e.target.value })}
            />
          </div>
          <div>
            <label className="ec-label">Body</label>
            <textarea
              className="ec-input min-h-[160px]"
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="ec-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="ec-btn-primary"
              disabled={save.isPending || !form.title.trim()}
            >
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function GenerateModal({
  state,
  onChangeText,
  pending,
  onGenerate,
  onClose,
}: {
  state: { text: string; result: GeneratedAids | null };
  onChangeText: (text: string) => void;
  pending: boolean;
  onGenerate: () => void;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-2xl overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold inline-flex items-center gap-2">
            <Sparkles size={16} className="text-brand-600" />
            Generate flashcards & MCQs
          </p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="space-y-3 p-5">
          <div>
            <label className="ec-label">Paste study text</label>
            <textarea
              className="ec-input min-h-[140px]"
              value={state.text}
              onChange={(e) => onChangeText(e.target.value)}
              placeholder="Paste lecture notes, a chapter, or any text you want to learn…"
            />
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              className="ec-btn-primary"
              disabled={pending || !state.text.trim()}
              onClick={onGenerate}
            >
              <Sparkles size={14} />
              {pending ? 'Generating…' : 'Generate'}
            </button>
          </div>
          {state.result && (
            <div className="space-y-4">
              {state.result.flashcards.length > 0 && (
                <div>
                  <p className="font-semibold text-sm mb-2">Flashcards</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {state.result.flashcards.map((f, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-border p-3 text-xs"
                      >
                        <p className="font-medium">{f.front}</p>
                        <p className="mt-1 text-ink-muted">{f.back}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {state.result.mcqs.length > 0 && (
                <div>
                  <p className="font-semibold text-sm mb-2">MCQs</p>
                  <ol className="space-y-2 text-xs">
                    {state.result.mcqs.map((m, i) => (
                      <li
                        key={i}
                        className="rounded-lg border border-border p-3"
                      >
                        <p className="font-medium">{m.question}</p>
                        <ul className="mt-1 list-disc pl-4 text-ink-muted">
                          {m.options.map((o, oi) => (
                            <li
                              key={oi}
                              className={
                                oi === m.answer
                                  ? 'text-emerald-600 font-medium'
                                  : ''
                              }
                            >
                              {o}
                            </li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function NoteActions({ noteId }: { noteId: string }) {
  const qc = useQueryClient();
  const [quiz, setQuiz] = useState<StudyQuiz | null>(null);
  const regen = useMutation({
    mutationFn: () =>
      academicDeepApi.regenerateStudyNote(noteId, { hint: 'improve clarity' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'study-notes'] });
      toast.success('Note regenerated');
    },
  });
  const openQuiz = useMutation({
    mutationFn: () => academicDeepApi.studyNoteQuiz(noteId),
    onSuccess: (data) => setQuiz(data),
    onError: () => toast.error('No MCQs on this note'),
  });
  return (
    <div className="flex flex-wrap gap-1 pt-1">
      <button
        type="button"
        className="ec-btn-ghost !px-2 !py-1 text-xs"
        onClick={() => regen.mutate()}
        disabled={regen.isPending}
      >
        <RefreshCw size={11} /> Regenerate
      </button>
      <button
        type="button"
        className="ec-btn-ghost !px-2 !py-1 text-xs"
        onClick={() => openQuiz.mutate()}
        disabled={openQuiz.isPending}
      >
        <PlayCircle size={11} /> Take quiz
      </button>
      {quiz && <QuizRunner quiz={quiz} onClose={() => setQuiz(null)} />}
    </div>
  );
}

function QuizRunner({
  quiz,
  onClose,
}: {
  quiz: StudyQuiz;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [score, setScore] = useState<{ score: number; total: number } | null>(
    null,
  );
  const submit = useMutation({
    mutationFn: () =>
      academicDeepApi.submitStudyQuizAttempt(quiz.note_id, answers),
    onSuccess: (data) => {
      setScore({ score: data.score, total: data.total });
      qc.invalidateQueries({
        queryKey: ['academic', 'study-aids', 'quiz-history'],
      });
    },
    onError: () => toast.error('Could not record attempt'),
  });
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">Quiz</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="space-y-4 p-5">
          {quiz.questions.map((q) => (
            <div key={q.index}>
              <p className="font-medium">{q.question}</p>
              <div className="mt-1 space-y-1">
                {q.options.map((o, i) => (
                  <label
                    key={i}
                    className="flex items-center gap-2 text-sm"
                  >
                    <input
                      type="radio"
                      name={`q-${q.index}`}
                      checked={answers[String(q.index)] === i}
                      onChange={() =>
                        setAnswers((a) => ({ ...a, [String(q.index)]: i }))
                      }
                    />
                    <span>{o}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
          {score && (
            <p className="rounded-lg bg-brand-600/10 p-3 text-sm font-medium">
              You scored {score.score}/{score.total}.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" className="ec-btn-secondary" onClick={onClose}>
              Close
            </button>
            <button
              type="button"
              className="ec-btn-primary"
              onClick={() => submit.mutate()}
              disabled={submit.isPending}
            >
              {submit.isPending ? 'Scoring…' : 'Submit'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function QuizHistoryPanel() {
  const q = useQuery({
    queryKey: ['academic', 'study-aids', 'quiz-history'],
    queryFn: () => academicDeepApi.myQuizHistory(),
  });
  if (q.isLoading) return null;
  const rows = q.data ?? [];
  if (!rows.length) return null;
  return (
    <section className="ec-card p-4">
      <p className="mb-2 inline-flex items-center gap-2 font-semibold">
        <History size={14} className="text-brand-600" />
        Recent quiz attempts
      </p>
      <ul className="space-y-1 text-sm">
        {rows.slice(0, 5).map((a) => (
          <li key={a.id} className="text-ink-muted">
            · {formatDateTime(a.taken_at)} — {a.score}/{a.total}
          </li>
        ))}
      </ul>
    </section>
  );
}
