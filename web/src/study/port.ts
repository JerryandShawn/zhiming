import type {
  GlossaryTerm,
  LearningSample,
  SearchQuery,
  StudyBundle,
  StudyMetadata,
  StudyPort,
  StudyScope,
  StudySystem,
  TermDetail,
  TermResolution,
  TermSummary,
} from './types';
import { normalize, StudyDataError, studySystems } from './validation';
import { readGlossary } from './validateGlossary';
import { readLearning } from './validateLearning';
const summary = ({ term_id, system, term, aliases }: GlossaryTerm): TermSummary => ({
  term_id,
  system,
  term,
  aliases: [...aliases],
});
const isSystem = (value: unknown): value is StudySystem => studySystems.some((item) => item === value);
const evidenceKey = (document: string, alias: string, claim: string) => JSON.stringify([document, alias, claim]);
function query(input: SearchQuery): SearchQuery {
  if (
    !input ||
    typeof input.text !== 'string' ||
    input.text.length > 1000 ||
    (input.system !== undefined && !isSystem(input.system))
  )
    throw new StudyDataError('INVALID_QUERY');
  return { text: normalize(input.text), system: input.system };
}
function termDetail(term: GlossaryTerm, bundle: StudyBundle, metadata: StudyMetadata): TermDetail {
  const sourceIds = new Set([
    ...term.sources.map((item) => item.source_id),
    ...term.school_differences.flatMap((item) => item.source_ids),
  ]);
  return structuredClone({
    term,
    sources: bundle.sources.sources.filter((item) => sourceIds.has(item.source_id)),
    metadata: metadata.glossary,
  });
}
function metadataFor(bundle: StudyBundle): StudyMetadata {
  const { version, stage, review_tag, entry_count, system_counts, limits } = bundle.terms;
  return {
    source_commit: bundle.learning[0].provenance.source_commit,
    mode: 'static-educational-only',
    glossary: {
      version,
      stage,
      review_tag,
      entry_count,
      system_counts,
      limits,
      source_count: bundle.sources.sources.length,
      source_stage: bundle.sources.stage,
    },
    learning: bundle.learning.map((item) => ({
      sample_id: item.sample_id,
      system: item.system,
      status: item.status,
      card_count: item.cards.length,
      limits: item.limits,
    })),
    effects: { model_calls: 0, business_writes: 0, progress_api: 'unavailable' },
  };
}
/** Static educational catalog only; no current-user authority or progress writes. */
export function createStudyPort(
  input: StudyBundle,
  wait: (signal?: AbortSignal) => Promise<void> = async () => {},
): StudyPort {
  const glossary = readGlossary(input.terms, input.sources);
  const samples = input.learning.map((sample) => readLearning(sample, sample.system));
  if (samples.length !== 3 || new Set(samples.map((item) => item.sample_id)).size !== 3) throw new StudyDataError();
  const bundle = structuredClone({ ...glossary, learning: samples }),
    metadata = metadataFor(bundle);
  let disposed = false;
  const scopes = new Set<StudyScope>();
  const alive = () => {
    if (disposed) throw new StudyDataError('DISPOSED');
  };
  function createScope(): StudyScope {
    alive();
    let generation = 0,
      closed = false,
      active: LearningSample | undefined;
    const check = () => {
      alive();
      if (closed) throw new StudyDataError('DISPOSED');
    };
    const reset = () => {
      generation++;
      active = undefined;
    };
    const begin = () => {
      check();
      reset();
      return generation;
    };
    const settled = async (id: number, signal?: AbortSignal) => {
      signal?.throwIfAborted();
      await wait(signal);
      signal?.throwIfAborted();
      check();
      if (id !== generation) throw new DOMException('Study viewer changed', 'AbortError');
    };
    const scope: StudyScope = {
      metadata() {
        check();
        return structuredClone(metadata);
      },
      reset,
      dispose() {
        reset();
        closed = true;
        scopes.delete(scope);
      },
      async search(input, signal) {
        const id = begin(),
          selected = query(input);
        await settled(id, signal);
        const rows = bundle.terms.entries
          .filter((term) => !selected.system || term.system === selected.system)
          .flatMap((term, index) => {
            const labels = [term.term, ...term.aliases].map(normalize),
              text = normalize(term.plain_explanation);
            const exact = labels.includes(selected.text),
              prefix = labels.some((label) => label.startsWith(selected.text));
            return !selected.text ||
              exact ||
              prefix ||
              labels.some((label) => label.includes(selected.text)) ||
              text.includes(selected.text)
              ? [{ term, score: exact ? 0 : prefix ? 1 : 2, index }]
              : [];
          });
        return {
          status: 'ready',
          value: rows.sort((a, b) => a.score - b.score || a.index - b.index).map(({ term }) => summary(term)),
        };
      },
      async resolveTerm(label, system, signal): Promise<TermResolution> {
        const id = begin(),
          selected = query({ text: label, system });
        if (!selected.text) throw new StudyDataError('INVALID_QUERY');
        await settled(id, signal);
        const candidates = bundle.terms.entries
          .filter(
            (term) =>
              (!selected.system || term.system === selected.system) &&
              [term.term, ...term.aliases].some((name) => normalize(name) === selected.text),
          )
          .map(summary);
        return !candidates.length
          ? { status: 'unavailable', message: '词典里暂时没有这个词；不会补造解释。' }
          : candidates.length === 1
            ? { status: 'resolved', term: candidates[0] }
            : { status: 'ambiguous', candidates };
      },
      async readTerm(termId, signal) {
        const id = begin();
        if (typeof termId !== 'string' || termId.length > 160) throw new StudyDataError('INVALID_QUERY');
        await settled(id, signal);
        const term = bundle.terms.entries.find((item) => item.term_id === termId);
        return term
          ? { status: 'ready', value: termDetail(term, bundle, metadata) }
          : { status: 'unavailable', message: '这个词条暂不可用，请重新选择。' };
      },
      async readLearning(sampleId, signal) {
        const id = begin();
        if (typeof sampleId !== 'string' || sampleId.length > 160) throw new StudyDataError('INVALID_QUERY');
        await settled(id, signal);
        const sample = bundle.learning.find((item) => item.sample_id === sampleId);
        if (!sample)
          return { status: 'unavailable', message: '此体系还没有这份学习卡样例；不会读取个人资料或临时计算。' };
        active = sample;
        return { status: 'ready', value: structuredClone(sample) };
      },
      resolveEvidence(ref) {
        if (disposed || closed || !active || !ref || ref.sample_id !== active.sample_id) return undefined;
        const key = evidenceKey(ref.document_id, ref.alias, ref.claim_id);
        const item = active.evidence.find((row) => evidenceKey(row.document_id, row.alias, row.claim_id) === key);
        return item ? structuredClone(item) : undefined;
      },
    };
    scopes.add(scope);
    return scope;
  }
  return {
    metadata() {
      alive();
      return structuredClone(metadata);
    },
    createScope,
    dispose() {
      if (disposed) return;
      for (const scope of [...scopes]) scope.dispose();
      disposed = true;
    },
  };
}
