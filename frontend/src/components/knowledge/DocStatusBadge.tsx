import { AlertTriangle, CheckCircle2, Clock, Cog, Loader2 } from 'lucide-react';
import { docStatusStyle } from '../../lib/knowledge';

type Props = { status: string; className?: string };

export function DocStatusBadge({ status, className }: Props) {
  const style = docStatusStyle(status);
  const Icon =
    status === 'ready'
      ? CheckCircle2
      : status === 'failed'
      ? AlertTriangle
      : status === 'parsing'
      ? Cog
      : status === 'embedding'
      ? Loader2
      : Clock;
  return (
    <span className={`${style.badge} ${className ?? ''}`}>
      <Icon
        size={11}
        className={status === 'embedding' || status === 'parsing' ? 'animate-spin' : ''}
      />
      <span className="ml-1">{style.label}</span>
    </span>
  );
}
