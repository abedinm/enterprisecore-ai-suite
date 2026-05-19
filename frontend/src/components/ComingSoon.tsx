import { Construction } from 'lucide-react';

type ComingSoonProps = {
  title: string;
  description?: string;
};

export function ComingSoon({ title, description }: ComingSoonProps) {
  return (
    <div className="grid min-h-[280px] place-items-center rounded-xl border border-dashed border-border bg-surface-muted/40 p-6 text-center">
      <div>
        <div className="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-full bg-surface-elevated">
          <Construction size={20} className="text-ink-muted" />
        </div>
        <p className="font-semibold">{title}</p>
        <p className="mt-1 text-sm text-ink-muted">
          {description ?? 'This panel is wired to its backend route but the UI is being built. The data table and forms will land in a follow-up commit.'}
        </p>
      </div>
    </div>
  );
}
