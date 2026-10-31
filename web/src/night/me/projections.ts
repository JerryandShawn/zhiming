import {
  AboutMeError,
  type AboutMeState,
  type AboutMeSnapshot,
  type AboutMeMemoryReceipt,
  type DeleteScope,
  type DeletePreview,
  type SourceRef,
  type SourceProjection,
} from './types';

export function sameRef(left: SourceRef, right: SourceRef) {
  return (
    left.messageId === right.messageId &&
    left.version === right.version &&
    left.start === right.start &&
    left.end === right.end &&
    left.quote === right.quote
  );
}
function permittedRefs(state: AboutMeState): SourceRef[] {
  return [
    ...state.memories.filter((item) => item.status !== 'deleted'),
    ...state.profileItems.filter((item) => item.status === 'active'),
    ...state.proposals.filter((item) => item.status !== 'deleted'),
    ...state.dictionary.filter((item) => item.status === 'active'),
  ].flatMap((item) => item.sourceRefs);
}
export function projectSource(state: AboutMeState, ref: SourceRef): SourceProjection {
  const source = state.sources.find((item) => item.id === ref.messageId);
  const unavailable = (reason: string): SourceProjection => ({ ref: { ...ref, quote: '' }, available: false, reason });
  if (!source || source.status !== 'active') return unavailable('原始来源已不可用。');
  if (source.revision !== ref.version) return unavailable('来源版本已变化，请重新读取。');
  const canonical = permittedRefs(state).find((candidate) => sameRef(candidate, ref));
  if (!canonical || Array.from(source.content).slice(ref.start, ref.end).join('') !== ref.quote)
    return unavailable('此条未提供可展示的授权节选。');
  return {
    ref: { ...canonical },
    available: true,
    quote: canonical.quote,
    label: `${canonical.at.slice(5, 10)} · ${canonical.channel === 'web-action' ? '本次用户编辑或确认' : canonical.channel === 'feishu' ? '飞书' : '网页'}`,
  };
}
export function previewDeletion(
  state: AboutMeState,
  factId: string,
  scope: DeleteScope,
  selected?: SourceRef,
): DeletePreview {
  const fact = state.memories.find((item) => item.id === factId && item.status !== 'deleted');
  if (!fact) throw new AboutMeError('NOT_FOUND', 404, '没有找到可删除的记忆，请重新查看。');
  if (!['fact', 'source'].includes(scope)) throw new AboutMeError('INVALID', 422, '请明确选择删除范围。');
  let sourceRef: SourceRef | undefined;
  if (scope === 'source') {
    const messageIds = [...new Set(fact.sourceRefs.map((ref) => ref.messageId))];
    sourceRef = selected
      ? fact.sourceRefs.find((ref) => sameRef(ref, selected))
      : messageIds.length === 1
        ? fact.sourceRefs[0]
        : undefined;
    if (!sourceRef || !projectSource(state, sourceRef).available)
      throw new AboutMeError('INVALID', 422, '请选择这条记忆中的一段可用来源，再核对删除范围。');
  }
  const hasSource = (refs: SourceRef[]) =>
    Boolean(sourceRef && refs.some((ref) => ref.messageId === sourceRef!.messageId));
  const affectedFactIds = state.memories
    .filter((item) => item.status !== 'deleted' && (scope === 'fact' ? item.id === factId : hasSource(item.sourceRefs)))
    .map((item) => item.id);
  const affectedProfileIds = state.profileItems
    .filter(
      (item) =>
        item.status === 'active' &&
        (item.factIds.some((id) => affectedFactIds.includes(id)) || hasSource(item.sourceRefs)),
    )
    .map((item) => item.id);
  const affectedProposalIds = state.proposals
    .filter(
      (item) =>
        item.status !== 'deleted' &&
        (Boolean(item.factId && affectedFactIds.includes(item.factId)) || hasSource(item.sourceRefs)),
    )
    .map((item) => item.id);
  const affectedSymbolIds = state.dictionary
    .filter((item) => item.status === 'active' && hasSource(item.sourceRefs))
    .map((item) => item.id);
  return {
    scope,
    targetId: factId,
    snapshotRevision: state.revision,
    targetRevision: fact.revision,
    ...(sourceRef ? { sourceRef: { ...sourceRef } } : {}),
    affectedFactIds,
    affectedProfileIds,
    affectedProposalIds,
    affectedSymbolIds,
    counts: {
      memories: affectedFactIds.length,
      profileItems: affectedProfileIds.length,
      proposals: affectedProposalIds.length,
      symbols: affectedSymbolIds.length,
    },
  };
}
export function projectSnapshot(state: AboutMeState): AboutMeSnapshot {
  const activeIds = new Set(state.memories.filter((item) => item.status === 'active').map((item) => item.id));
  return {
    revision: state.revision,
    profileItems: state.profileItems,
    memories: state.memories,
    proposals: state.proposals,
    people: state.people
      .map((person) => ({ ...person, memoryIds: person.memoryIds.filter((id) => activeIds.has(id)) }))
      .filter((person) => person.memoryIds.length),
    timeline: state.timeline
      .filter((item) => item.memoryIds.some((id) => activeIds.has(id)))
      .map((item) => ({ ...item, memoryIds: item.memoryIds.filter((id) => activeIds.has(id)) })),
    dictionary: state.dictionary,
    autoSaveCategories: state.autoSaveCategories,
    lastOrganizedAt: state.lastOrganizedAt,
  };
}
export function currentMemoryReceipts(state: AboutMeState): AboutMeMemoryReceipt[] {
  const facts = state.memories.map((item): AboutMeMemoryReceipt => ({
    fact_id: item.id,
    proposal_id: item.proposalId,
    write_status: item.status === 'active' ? 'saved' : item.status,
    summary: item.text,
    revision: item.revision,
    category: item.category,
    ...(item.categorySaved ? { category_saved: true } : {}),
  }));
  const proposals = state.proposals
    .filter((item) => !item.factId || !state.memories.some((fact) => fact.id === item.factId))
    .map((item): AboutMeMemoryReceipt => ({
      proposal_id: item.id,
      write_status: item.status === 'pending' ? 'pending_confirmation' : item.status,
      summary: item.text,
      revision: item.revision,
      category: item.category,
      ...(item.categorySaved ? { category_saved: true } : {}),
    }));
  return [...facts, ...proposals];
}
