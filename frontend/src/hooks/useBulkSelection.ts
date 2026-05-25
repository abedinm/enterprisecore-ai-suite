/**
 * useBulkSelection — small hook to power the "select many rows in a list"
 * UX that's missing everywhere in EnterpriseCore today.
 *
 * Usage:
 *   const sel = useBulkSelection(rows.map(r => r.id));
 *   <input
 *     type="checkbox"
 *     checked={sel.isSelected(row.id)}
 *     onChange={() => sel.toggle(row.id)}
 *     aria-label={`Select ${row.name}`}
 *   />
 *   <BulkActionBar count={sel.size} onClear={sel.clear}>
 *     <button onClick={() => deleteMany(sel.ids)}>Delete</button>
 *   </BulkActionBar>
 *
 * Features:
 *   - Shift-click range selection (call ``shiftToggle(id)`` from a shift-
 *     clicked row to extend selection between the last anchor and id).
 *   - Select-all / clear-all.
 *   - Selection automatically prunes ids that disappear from the underlying
 *     list (e.g. after a delete) so the action bar doesn't lie about counts.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export function useBulkSelection<TId extends string | number>(allIds: TId[]) {
  const [selected, setSelected] = useState<Set<TId>>(() => new Set());
  const lastAnchor = useRef<TId | null>(null);

  // Prune disappeared ids on every list change.
  useEffect(() => {
    const valid = new Set(allIds);
    setSelected((prev) => {
      let changed = false;
      const next = new Set<TId>();
      for (const id of prev) {
        if (valid.has(id)) next.add(id);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [allIds]);

  const toggle = useCallback((id: TId) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      lastAnchor.current = id;
      return next;
    });
  }, []);

  const shiftToggle = useCallback(
    (id: TId) => {
      const anchor = lastAnchor.current;
      if (anchor === null) {
        toggle(id);
        return;
      }
      const startIdx = allIds.indexOf(anchor);
      const endIdx = allIds.indexOf(id);
      if (startIdx === -1 || endIdx === -1) {
        toggle(id);
        return;
      }
      const [lo, hi] = startIdx <= endIdx ? [startIdx, endIdx] : [endIdx, startIdx];
      setSelected((prev) => {
        const next = new Set(prev);
        for (let i = lo; i <= hi; i++) next.add(allIds[i]);
        return next;
      });
    },
    [allIds, toggle],
  );

  const selectAll = useCallback(() => {
    setSelected(new Set(allIds));
  }, [allIds]);

  const clear = useCallback(() => {
    setSelected(new Set());
    lastAnchor.current = null;
  }, []);

  const ids = useMemo(() => Array.from(selected), [selected]);
  const isSelected = useCallback((id: TId) => selected.has(id), [selected]);
  const all = allIds.length > 0 && selected.size === allIds.length;
  const some = selected.size > 0 && !all;

  return {
    ids,
    size: selected.size,
    isSelected,
    toggle,
    shiftToggle,
    selectAll,
    clear,
    allChecked: all,
    indeterminate: some,
  };
}
