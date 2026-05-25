/**
 * TableSkipLink — sr-only-until-focused anchor that jumps past a long
 * data table. Pair with a sibling element whose id matches `targetId`
 * (typically right after the </table>).
 *
 *   <TableSkipLink targetId="after-invoices" label="Skip invoices table" />
 *   <table>…</table>
 *   <div id="after-invoices" tabIndex={-1} />
 */
export type TableSkipLinkProps = {
  targetId: string;
  label?: string;
};

export function TableSkipLink({ targetId, label = 'Skip table' }: TableSkipLinkProps) {
  return (
    <a
      href={`#${targetId}`}
      className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:rounded-md focus:border focus:border-border focus:bg-surface-elevated focus:px-3 focus:py-1 focus:text-sm focus:font-medium focus:text-brand-700 focus:shadow-card"
    >
      {label}
    </a>
  );
}
