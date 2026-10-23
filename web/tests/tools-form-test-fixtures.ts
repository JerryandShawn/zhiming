import fs from 'node:fs';
import path from 'node:path';
import { vi } from 'vitest';
import { createToolDemoPort } from '../src/tools/port';
import type { PublishedSample, SynastrySample, ToolPort, WindowSample } from '../src/tools/types';

const files = [
  'window-search-ayuan-contract-20261021-27.json',
  'window-search-ayuan-page2.json',
  'window-search-ayuan-empty.json',
  'synastry-ayuan-xiaohe.json',
] as const;
const publicDirectory = path.resolve('public/data/tools');
let originals: PublishedSample[] | undefined;
function samples() {
  originals ??= files.map(
    (file) => JSON.parse(fs.readFileSync(path.join(publicDirectory, file), 'utf8')) as PublishedSample,
  );
  // The production port validates its catalog and clones these original public
  // projection bytes. No minimal fake chart, altered source data or HTTP call.
  return structuredClone(originals);
}

export function countedTools(options: { failWindow?: number; failSynastry?: number } = {}) {
  const published = samples(),
    real = createToolDemoPort(published);
  let windowFailures = options.failWindow ?? 0,
    synastryFailures = options.failSynastry ?? 0;
  const wrap = (inner: ToolPort): ToolPort => ({
    windows: inner.windows,
    reset: vi.fn(inner.reset),
    createScope: vi.fn(() => wrap(inner.createScope())),
    resolveEvidence: vi.fn(inner.resolveEvidence),
    windowSearch: vi.fn(async (query, signal) => {
      if (windowFailures-- > 0) throw new Error('Synthetic transient window read failure');
      return inner.windowSearch(query, signal);
    }),
    synastry: vi.fn(async (query, consent, signal) => {
      if (synastryFailures-- > 0) throw new Error('Synthetic transient synastry read failure');
      return inner.synastry(query, consent, signal);
    }),
  });
  const port = wrap(real);
  return {
    port,
    windows: published.filter((item): item is WindowSample => item.tool === 'window_search'),
    synastry: published.find((item): item is SynastrySample => item.tool === 'synastry')!,
    windowReads: vi.mocked(port.windowSearch),
    synastryReads: vi.mocked(port.synastry),
  };
}
