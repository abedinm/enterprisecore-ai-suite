import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  Check,
  Image as ImageIcon,
  Loader2,
  Trash2,
  Upload as UploadIcon,
  X,
} from 'lucide-react';
import { marketingApi, type MarketingUpload } from '../../lib/marketing';
import { formatDate } from '../../lib/utils';

function humanSize(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/**
 * Generic uploader + grid. Used both as the standalone /marketing/media page
 * and as the body of <MediaPickerDialog />. The `onPick` callback turns each
 * tile into a selectable button; without it, tiles are passive.
 */
export function MediaGrid({
  onPick,
  selectedId,
}: {
  onPick?: (upload: MarketingUpload) => void;
  selectedId?: string | null;
}) {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement | null>(null);

  const uploadsQ = useQuery({
    queryKey: ['marketing', 'uploads'],
    queryFn: () => marketingApi.listUploads(),
  });

  const upload = useMutation({
    mutationFn: (file: File) => marketingApi.uploadFile(file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'uploads'] });
      toast.success('Uploaded');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
        .response?.data?.detail ?? (err as Error).message ?? 'Upload failed';
      toast.error(typeof detail === 'string' ? detail : 'Upload failed');
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => marketingApi.deleteUpload(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marketing', 'uploads'] });
      toast.success('Deleted');
    },
  });

  function onFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    upload.mutate(file);
    e.target.value = ''; // reset for re-pick
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm text-ink-muted">
          {uploadsQ.data?.length ?? 0} files
        </div>
        <div>
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={onFilePicked}
          />
          <button
            type="button"
            className="ec-btn-primary"
            onClick={() => inputRef.current?.click()}
            disabled={upload.isPending}
          >
            {upload.isPending ? (
              <>
                <Loader2 size={16} className="animate-spin" /> Uploading…
              </>
            ) : (
              <>
                <UploadIcon size={16} /> Upload image
              </>
            )}
          </button>
        </div>
      </div>

      {uploadsQ.isLoading && (
        <p className="text-sm text-ink-muted">Loading media…</p>
      )}

      {uploadsQ.data && uploadsQ.data.length === 0 && (
        <div className="grid place-items-center rounded-xl border border-dashed border-border bg-surface-muted/40 p-10 text-center">
          <ImageIcon size={28} className="mb-3 text-ink-subtle" />
          <p className="font-semibold">No media yet</p>
          <p className="mt-1 text-sm text-ink-muted">
            Upload your first image to use it across projects, team, and sections.
          </p>
        </div>
      )}

      {uploadsQ.data && uploadsQ.data.length > 0 && (
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {uploadsQ.data.map((file) => {
            const isImage = file.contentType.startsWith('image/');
            const selected = selectedId === file.id;
            const TileTag = onPick ? 'button' : 'div';
            return (
              <div
                key={file.id}
                className="ec-card group relative overflow-hidden p-0"
              >
                <TileTag
                  type={onPick ? 'button' : undefined}
                  onClick={onPick ? () => onPick(file) : undefined}
                  className={
                    'block w-full text-left transition ' +
                    (onPick ? 'cursor-pointer hover:bg-surface-muted/30' : '')
                  }
                >
                  <div className="aspect-square w-full overflow-hidden bg-surface-muted">
                    {isImage ? (
                      <img
                        src={file.url}
                        alt={file.filename}
                        className="h-full w-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <div className="grid h-full w-full place-items-center text-ink-subtle">
                        <ImageIcon size={28} />
                      </div>
                    )}
                  </div>
                  <div className="p-2.5">
                    <p className="truncate text-xs font-medium" title={file.filename}>
                      {file.filename}
                    </p>
                    <p className="mt-0.5 flex items-center justify-between text-[11px] text-ink-subtle">
                      <span>{humanSize(file.sizeBytes)}</span>
                      <span>{formatDate(file.createdAt)}</span>
                    </p>
                  </div>
                </TileTag>
                {selected && (
                  <div className="absolute right-2 top-2 grid h-6 w-6 place-items-center rounded-full bg-brand-600 text-white">
                    <Check size={14} />
                  </div>
                )}
                {!onPick && (
                  <button
                    type="button"
                    className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-full bg-rose-600 text-white opacity-0 transition group-hover:opacity-100"
                    onClick={() => {
                      if (confirm(`Delete ${file.filename}?`)) remove.mutate(file.id);
                    }}
                    title="Delete"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function MarketingMediaPage() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Media library</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Upload images once and reference them across projects, team, and sections.
        </p>
      </div>
      <MediaGrid />
    </div>
  );
}

/* -------------------------------------------------------------------------- */

/** Modal wrapper around <MediaGrid />. Returns the picked upload via onPick. */
export function MediaPickerDialog({
  open,
  selectedId,
  onClose,
  onPick,
}: {
  open: boolean;
  selectedId?: string | null;
  onClose: () => void;
  onPick: (upload: MarketingUpload) => void;
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">Pick an image</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto p-5">
          <MediaGrid
            selectedId={selectedId}
            onPick={(u) => {
              onPick(u);
              onClose();
            }}
          />
        </div>
      </div>
    </div>
  );
}
