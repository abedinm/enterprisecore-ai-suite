import { Fragment } from 'react';

type Props = {
  text: string;
  highlightIndex: number | null;
  onCite: (index: number) => void;
};

/** Render assistant text and turn [1] [2] ... patterns into clickable badges
 *  so the user can hover/click to focus the matching source card. */
export function CitationText({ text, highlightIndex, onCite }: Props) {
  const pattern = /\[(\d{1,3})\]/g;
  const parts: (string | { idx: number; raw: string })[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    const idx = parseInt(match[1], 10);
    if (match.index > last) parts.push(text.slice(last, match.index));
    parts.push({ idx, raw: match[0] });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));

  return (
    <span className="whitespace-pre-wrap font-sans">
      {parts.map((p, i) => {
        if (typeof p === 'string') return <Fragment key={i}>{p}</Fragment>;
        const isActive = highlightIndex === p.idx;
        return (
          <button
            key={i}
            type="button"
            onClick={() => onCite(p.idx)}
            className={`mx-0.5 inline-flex h-4 min-w-[18px] items-center justify-center rounded-full px-1 text-[10px] font-bold transition ${
              isActive
                ? 'bg-brand-600 text-white'
                : 'bg-brand-100 text-brand-700 hover:bg-brand-200 dark:bg-brand-900/30 dark:text-brand-300'
            }`}
            title={`Source ${p.idx}`}
          >
            {p.idx}
          </button>
        );
      })}
    </span>
  );
}
