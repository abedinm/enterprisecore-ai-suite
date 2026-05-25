import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import toast from 'react-hot-toast';
import { Database } from 'lucide-react';
import { KbDialog } from '../../components/knowledge/KbDialog';
import { KbList } from '../../components/knowledge/KbList';
import { knowledgeApi, type KbCreateIn, type KbOut } from '../../lib/knowledge';
import { KnowledgeDocumentsPanel } from './KnowledgeDocumentsPanel';

export function KnowledgeTab() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<KbOut | null>(null);

  const kbsQuery = useQuery({
    queryKey: ['knowledge', 'kbs'],
    queryFn: knowledgeApi.listKbs,
    refetchInterval: 10_000,
  });

  const createOrUpdate = useMutation({
    mutationFn: async (body: KbCreateIn) => {
      if (editing) return knowledgeApi.updateKb(editing.id, body);
      return knowledgeApi.createKb(body);
    },
    onSuccess: (kb) => {
      qc.invalidateQueries({ queryKey: ['knowledge', 'kbs'] });
      setSelected(kb.id);
      toast.success(editing ? 'KB updated' : 'KB created');
    },
  });

  const deleteKb = useMutation({
    mutationFn: (id: string) => knowledgeApi.deleteKb(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['knowledge', 'kbs'] });
      if (selected === id) setSelected(null);
      toast.success('KB deleted');
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'Delete failed'),
  });

  const selectedKb = kbsQuery.data?.find((k) => k.id === selected) ?? null;

  return (
    <div className="grid h-[calc(100vh-22rem)] min-h-[480px] gap-3 lg:grid-cols-[260px_1fr]">
      <KbList
        kbs={kbsQuery.data ?? []}
        loading={kbsQuery.isLoading}
        selectedId={selected}
        onSelect={setSelected}
        onCreate={() => {
          setEditing(null);
          setDialogOpen(true);
        }}
        onEdit={(kb) => {
          setEditing(kb);
          setDialogOpen(true);
        }}
        onDelete={(kb) => {
          if (confirm(`Delete "${kb.name}" and all its documents? This cannot be undone.`)) {
            deleteKb.mutate(kb.id);
          }
        }}
      />

      <section className="overflow-hidden rounded-xl border border-border bg-surface-elevated">
        {!selectedKb ? (
          <div className="grid h-full place-items-center p-10 text-center">
            <div>
              <Database size={32} className="mx-auto mb-3 text-ink-subtle" />
              <p className="text-sm font-medium text-ink">No knowledge base selected</p>
              <p className="mt-1 max-w-sm text-xs text-ink-muted">
                Create a KB on the left, then upload PDFs, DOCX, Markdown or plain
                text — your documents stay on this machine and get embedded with
                your chosen model.
              </p>
            </div>
          </div>
        ) : (
          <KnowledgeDocumentsPanel kb={selectedKb} />
        )}
      </section>

      <KbDialog
        open={dialogOpen}
        initial={editing}
        onClose={() => setDialogOpen(false)}
        onSubmit={async (body) => {
          await createOrUpdate.mutateAsync(body);
        }}
      />
    </div>
  );
}
