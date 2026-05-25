/**
 * The chat panel needs to parse AI responses that interleave prose with one or
 * more fenced code blocks, because the "Insert →" button targets the code blocks
 * specifically. The parser lives in ChatPanel.tsx; we replicate it here so the
 * unit tests don't have to render React.
 */
import { describe, expect, it } from 'vitest';

type Block = { kind: 'text' | 'code'; content: string; language?: string };

function splitCodeBlocks(text: string): Block[] {
  const out: Block[] = [];
  const re = /```([\w+-]*)\n([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push({ kind: 'text', content: text.slice(last, m.index).trim() });
    out.push({ kind: 'code', content: m[2].replace(/\n+$/, ''), language: m[1] });
    last = re.lastIndex;
  }
  if (last < text.length) out.push({ kind: 'text', content: text.slice(last).trim() });
  return out.filter((b) => b.content.length > 0);
}

describe('splitCodeBlocks', () => {
  it('returns a single text block when no fences are present', () => {
    expect(splitCodeBlocks('plain prose only')).toEqual([
      { kind: 'text', content: 'plain prose only' },
    ]);
  });

  it('parses one fenced block with a language tag', () => {
    const out = splitCodeBlocks('Here is the code:\n```python\nprint(1)\n```\nDone.');
    expect(out).toEqual([
      { kind: 'text', content: 'Here is the code:' },
      { kind: 'code', language: 'python', content: 'print(1)' },
      { kind: 'text', content: 'Done.' },
    ]);
  });

  it('parses multiple blocks interspersed with prose', () => {
    const text = 'First:\n```js\na()\n```\nThen:\n```ts\nb()\n```\nFinis.';
    const out = splitCodeBlocks(text);
    expect(out).toHaveLength(5);
    expect(out[0]).toEqual({ kind: 'text', content: 'First:' });
    expect(out[1]).toEqual({ kind: 'code', language: 'js', content: 'a()' });
    expect(out[2]).toEqual({ kind: 'text', content: 'Then:' });
    expect(out[3]).toEqual({ kind: 'code', language: 'ts', content: 'b()' });
    expect(out[4]).toEqual({ kind: 'text', content: 'Finis.' });
  });

  it('handles a fenced block with no language', () => {
    const out = splitCodeBlocks('```\necho hi\n```');
    expect(out).toEqual([
      { kind: 'code', language: '', content: 'echo hi' },
    ]);
  });

  it('drops trailing blank lines inside code content', () => {
    const out = splitCodeBlocks('```python\nprint(1)\n\n\n```');
    expect(out).toEqual([
      { kind: 'code', language: 'python', content: 'print(1)' },
    ]);
  });

  it('ignores empty text segments between adjacent blocks', () => {
    const out = splitCodeBlocks('```js\na\n```\n```ts\nb\n```');
    expect(out).toHaveLength(2);
    expect(out.every((b) => b.kind === 'code')).toBe(true);
  });
});
