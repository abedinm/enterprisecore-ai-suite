import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import type { KbCreateIn, KbOut } from '../../lib/knowledge';

type Props = {
  open: boolean;
  initial?: KbOut | null;
  onClose: () => void;
  onSubmit: (body: KbCreateIn) => Promise<void>;
};

const EMBEDDING_OPTIONS: { provider: string; model: string; dim: number; label: string }[] = [
  { provider: 'ollama', model: 'nomic-embed-text', dim: 768, label: 'Ollama · nomic-embed-text (768d, free, offline)' },
  { provider: 'ollama', model: 'mxbai-embed-large', dim: 1024, label: 'Ollama · mxbai-embed-large (1024d, free, offline)' },
  { provider: 'ollama', model: 'all-minilm', dim: 384, label: 'Ollama · all-minilm (384d, smallest, offline)' },
  { provider: 'openai', model: 'text-embedding-3-small', dim: 1536, label: 'OpenAI · text-embedding-3-small (1536d, paid)' },
  { provider: 'openai', model: 'text-embedding-3-large', dim: 3072, label: 'OpenAI · text-embedding-3-large (3072d, paid)' },
];

export function KbDialog({ open, initial, onClose, onSubmit }: Props) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [embeddingChoice, setEmbeddingChoice] = useState(0);
  const [chunkSize, setChunkSize] = useState(800);
  const [chunkOverlap, setChunkOverlap] = useState(100);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? '');
    setDescription(initial?.description ?? '');
    setChunkSize(initial?.chunk_size ?? 800);
    setChunkOverlap(initial?.chunk_overlap ?? 100);
    const matchedIdx = initial
      ? EMBEDDING_OPTIONS.findIndex(
          (o) => o.provider === initial.embedding_provider && o.model === initial.embedding_model,
        )
      : 0;
    setEmbeddingChoice(matchedIdx >= 0 ? matchedIdx : 0);
    setError(null);
    setBusy(false);
  }, [open, initial]);

  if (!open) return null;

  const chosen = EMBEDDING_OPTIONS[embeddingChoice];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError('Name is required');
      return;
    }
    if (chunkOverlap >= chunkSize) {
      setError('Overlap must be smaller than chunk size');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim() || null,
        embedding_provider: chosen.provider,
        embedding_model: chosen.model,
        embedding_dim: chosen.dim,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
      });
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'Failed to save');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 px-4 py-8"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <form
        className="w-full max-w-lg rounded-xl border border-border bg-surface-elevated shadow-xl"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="text-base font-semibold">
            {initial ? 'Edit knowledge base' : 'New knowledge base'}
          </h3>
          <button type="button" className="ec-btn-ghost !p-1.5" onClick={onClose}>
            <X size={14} />
          </button>
        </div>

        <div className="space-y-4 p-4">
          <div>
            <label className="ec-label">Name</label>
            <input
              autoFocus
              className="ec-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Engineering Wiki"
              maxLength={200}
            />
          </div>

          <div>
            <label className="ec-label">Description</label>
            <textarea
              className="ec-input min-h-[60px]"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What lives in this KB?"
            />
          </div>

          <div>
            <label className="ec-label">Embedding model</label>
            <select
              className="ec-input"
              value={embeddingChoice}
              onChange={(e) => setEmbeddingChoice(parseInt(e.target.value, 10))}
              disabled={!!initial}
            >
              {EMBEDDING_OPTIONS.map((opt, i) => (
                <option key={`${opt.provider}-${opt.model}`} value={i}>
                  {opt.label}
                </option>
              ))}
            </select>
            {initial && (
              <p className="mt-1 text-xs text-ink-subtle">
                Changing the embedding model after creation requires a full re-embed; not yet exposed in the UI.
              </p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="ec-label">Chunk size (chars)</label>
              <input
                type="number"
                className="ec-input"
                value={chunkSize}
                min={200}
                max={4000}
                step={50}
                onChange={(e) => setChunkSize(parseInt(e.target.value || '0', 10))}
              />
            </div>
            <div>
              <label className="ec-label">Overlap (chars)</label>
              <input
                type="number"
                className="ec-input"
                value={chunkOverlap}
                min={0}
                max={800}
                step={10}
                onChange={(e) => setChunkOverlap(parseInt(e.target.value || '0', 10))}
              />
            </div>
          </div>

          {error && (
            <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900/40 dark:bg-rose-900/20 dark:text-rose-300">
              {error}
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border bg-surface-muted px-4 py-3">
          <button type="button" className="ec-btn-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ec-btn-primary" disabled={busy}>
            {busy ? 'Saving…' : initial ? 'Save changes' : 'Create KB'}
          </button>
        </div>
      </form>
    </div>
  );
}
