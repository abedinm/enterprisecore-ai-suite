import { describe, expect, it } from 'vitest';
import { flattenFiles } from '../FileTree';
import type { FileNode } from '../types';

const TREE: FileNode = {
  name: 'root', path: '/r', is_dir: true, size: null,
  children: [
    { name: 'src', path: '/r/src', is_dir: true, size: null, children: [
      { name: 'a.ts', path: '/r/src/a.ts', is_dir: false, size: 10 },
      { name: 'b.tsx', path: '/r/src/b.tsx', is_dir: false, size: 20 },
    ]},
    { name: 'README.md', path: '/r/README.md', is_dir: false, size: 30 },
  ],
};

describe('FileTree helpers', () => {
  it('flattenFiles returns only files, in pre-order', () => {
    expect(flattenFiles(TREE)).toEqual([
      '/r/src/a.ts',
      '/r/src/b.tsx',
      '/r/README.md',
    ]);
  });

  it('flattenFiles returns [] for null input', () => {
    expect(flattenFiles(null)).toEqual([]);
  });

  it('flattenFiles skips directories themselves', () => {
    const just_dirs: FileNode = {
      name: 'r', path: '/r', is_dir: true, size: null,
      children: [
        { name: 'a', path: '/r/a', is_dir: true, size: null, children: [] },
      ],
    };
    expect(flattenFiles(just_dirs)).toEqual([]);
  });
});
