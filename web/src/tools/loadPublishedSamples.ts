import { createToolDemoPort, ToolViewError } from './port';
import type { PublishedSample, ToolName, ToolPort } from './types';

export const sampleFiles = [
  'window-search-ayuan-contract-20261021-27.json',
  'window-search-ayuan-page2.json',
  'window-search-ayuan-empty.json',
  'synastry-ayuan-xiaohe.json',
] as const;
type SampleFile = (typeof sampleFiles)[number];
type Entry = { file: SampleFile; tool: ToolName; document_id: string; sha256: string };
type Manifest = { source_commit: string; entries: Entry[] };
const invalid = () => new ToolViewError('INVALID_PUBLIC_SAMPLE');
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const hex = (value: unknown, length: number): value is string =>
  typeof value === 'string' && new RegExp(`^[a-f0-9]{${length}}$`).test(value);
const documentId = (value: unknown): value is string => typeof value === 'string' && /^tool-[a-f0-9]{64}$/.test(value);
const fileTool = (file: string): ToolName => (file.startsWith('window-') ? 'window_search' : 'synastry');

export function readManifest(value: unknown): Manifest {
  if (
    !record(value) ||
    value.schema !== 'frontend-tools-export-v1' ||
    value.source_ref !== 'origin/v4/p8-calc' ||
    !hex(value.source_commit, 40) ||
    value.synthetic_only !== true ||
    value.model_calls !== 0 ||
    !Array.isArray(value.entries) ||
    value.entries.length !== sampleFiles.length
  )
    throw invalid();
  const entries: Entry[] = [];
  for (const entry of value.entries) {
    if (
      !record(entry) ||
      typeof entry.file !== 'string' ||
      !sampleFiles.includes(entry.file as SampleFile) ||
      entry.tool !== fileTool(entry.file) ||
      !documentId(entry.document_id) ||
      !hex(entry.sha256, 64) ||
      entries.some((old) => old.file === entry.file || old.document_id === entry.document_id)
    )
      throw invalid();
    entries.push({
      file: entry.file as SampleFile,
      tool: fileTool(entry.file),
      document_id: entry.document_id,
      sha256: entry.sha256,
    });
  }
  return { source_commit: value.source_commit, entries };
}

export function readPublicSample(value: unknown, entry: Entry, commit: string): PublishedSample {
  const publicKeys = new Set(['format', 'tool', 'document_id', 'data', 'evidence', 'effects', 'limits', 'provenance']);
  if (
    !record(value) ||
    Object.keys(value).some((key) => !publicKeys.has(key)) ||
    value.format !== 'frontend-tool-sample-v1' ||
    value.tool !== entry.tool ||
    value.document_id !== entry.document_id ||
    !record(value.data) ||
    !Array.isArray(value.evidence) ||
    !Array.isArray(value.limits) ||
    !value.limits.every((item) => typeof item === 'string') ||
    !record(value.effects) ||
    value.effects.model_calls !== 0 ||
    value.effects.writes !== 0 ||
    value.effects.alias_registry !== 'ephemeral_only' ||
    !record(value.provenance) ||
    value.provenance.source_ref !== 'origin/v4/p8-calc' ||
    value.provenance.source_commit !== commit ||
    value.provenance.source_path !== `docs/v4/contracts/samples/${entry.file}` ||
    !hex(value.provenance.source_sha256, 64) ||
    value.provenance.mode !== 'published-synthetic-engine' ||
    value.provenance.integrity !== 'root-document-pointer-alias-and-fact-digests-verified'
  )
    throw invalid();
  // These bytes must also match the static manifest; the offline exporter owns
  // complete scientific projection validation, then the port checks alias scope.
  return value as unknown as PublishedSample;
}

async function download(filename: string, signal?: AbortSignal) {
  const response = await fetch(`/data/tools/${filename}`, {
    signal,
    cache: 'no-store',
    credentials: 'omit',
    redirect: 'error',
  });
  if (!response.ok) throw invalid();
  const body = await response.arrayBuffer();
  if (!body.byteLength || body.byteLength > 4 * 1024 * 1024) throw invalid();
  return body;
}
const parse = (body: ArrayBuffer): unknown => JSON.parse(new TextDecoder().decode(body));
const digest = async (body: ArrayBuffer) =>
  Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', body)), (value) =>
    value.toString(16).padStart(2, '0'),
  ).join('');

/** Only fixed public static files; this seam makes no /api request or writes. */
export async function loadPublishedToolPort(signal?: AbortSignal): Promise<ToolPort> {
  const manifest = readManifest(parse(await download('manifest.json', signal)));
  const samples = await Promise.all(
    manifest.entries.map(async (entry) => {
      const body = await download(entry.file, signal);
      if ((await digest(body)) !== entry.sha256) throw invalid();
      return readPublicSample(parse(body), entry, manifest.source_commit);
    }),
  );
  signal?.throwIfAborted();
  return createToolDemoPort(samples);
}
