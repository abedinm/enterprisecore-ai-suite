/**
 * Skeleton — a placeholder block that shimmers while real content loads.
 *
 *   <Skeleton className="h-4 w-32" />
 *   <SkeletonCircle size={40} />
 *   <SkeletonRow lines={3} />
 *
 * Pair with the existing `.ec-shimmer` global class. Designed to be composable
 * — drop these into list cells, card placeholders, modal bodies. The aim is to
 * eliminate spinners in favour of content-shaped loading states.
 */
import { type CSSProperties } from 'react';

export function Skeleton({ className = '', style }: { className?: string; style?: CSSProperties }) {
  return (
    <div
      className={`ec-shimmer rounded-md ${className}`}
      style={style}
      aria-hidden="true"
    />
  );
}

export function SkeletonCircle({ size = 32, className = '' }: { size?: number; className?: string }) {
  return (
    <div
      className={`ec-shimmer rounded-full ${className}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  );
}

export function SkeletonRow({
  lines = 3,
  className = '',
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={`h-3 ${i === lines - 1 ? 'w-2/3' : 'w-full'}`}
        />
      ))}
    </div>
  );
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`ec-card-static p-4 ${className}`}>
      <div className="flex items-center gap-3">
        <SkeletonCircle size={40} />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-3 w-1/2" />
          <Skeleton className="h-3 w-1/3" />
        </div>
      </div>
      <SkeletonRow lines={3} className="mt-4" />
    </div>
  );
}
