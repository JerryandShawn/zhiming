import { hasBirthFields } from '../../chat/publicProjection';
import { sourceRef } from './fixtures';
import { currentMemoryReceipts, previewDeletion, projectSource } from './projections';
import {
  AboutMeError,
  PROFILE_SECTIONS,
  type AboutMeCommand,
  type AboutMeReceipt,
  type AboutMeState,
  type MemoryItem,
  type ModelContext,
  type ProposalItem,
  type SourceRecord,
} from './types';

export function safeText(value: string): string {
  const text = typeof value === 'string' ? value.trim() : '';
  if (!text || Array.from(text).length > 2000) throw new AboutMeError('INVALID', 422, '请填写1至2000字的内容。');
  if (hasBirthFields(text))
    throw new AboutMeError('INVALID', 422, '出生原值请到专门的资料确认界面核对，这里只保存安全摘要。');
  return text;
}
function target<T extends { id: string; revision: number; status: string }>(
  items: T[],
  command: { id: string; expectedRevision: number },
): T {
  const item = items.find((row) => row.id === command.id);
  if (!item) throw new AboutMeError('NOT_FOUND', 404, '没有找到这条记录，请重新查看。');
  if (item.revision !== command.expectedRevision || item.status === 'deleted')
    throw new AboutMeError('CONFLICT', 409, '这条记录已变化，请读取最新版本并核对，草稿仍保留。');
  return item;
}
function editSource(state: AboutMeState, text: string, context: ModelContext): SourceRecord {
  const source: SourceRecord = {
    id: context.newId('user-source'),
    revision: 1,
    role: 'user',
    status: 'active',
    channel: 'web-action',
    at: context.at,
    content: text,
  };
  state.sources.push(source);
  return source;
}
function newMemory(
  state: AboutMeState,
  id: string,
  text: string,
  source: SourceRecord,
  context: ModelContext,
): MemoryItem {
  if (state.revokedFactIds.includes(id) || state.memories.some((item) => item.id === id))
    throw new AboutMeError('CONFLICT', 409, '这条事实已存在或已撤回，不能从旧事件重新建立。');
  const memory: MemoryItem = {
    id,
    text,
    revision: 1,
    status: 'active',
    sourceRefs: [sourceRef(source, text)],
    createdAt: context.at,
    updatedAt: context.at,
  };
  state.memories.push(memory);
  return memory;
}
function profileEdit(
  state: AboutMeState,
  command: Extract<AboutMeCommand, { type: 'profile-edit' }>,
  context: ModelContext,
) {
  const text = safeText(command.text);
  let item = state.profileItems.find((row) => row.id === command.id);
  if (item) item = target(state.profileItems, command);
  else {
    if (command.expectedRevision !== 0 || !PROFILE_SECTIONS.some((section) => section.id === command.section))
      throw new AboutMeError('INVALID', 422, '新画像条目需要明确分节并从版本0创建。');
    item = {
      id: command.id,
      section: command.section!,
      text: '',
      revision: 0,
      updatedAt: context.at,
      sourceIds: [],
      factIds: [],
      sourceRefs: [],
      confidence: 1,
      pinned: false,
      userEdited: false,
      status: 'active',
    };
    state.profileItems.push(item);
  }
  if (command.section && command.section !== item.section)
    throw new AboutMeError('INVALID', 422, '编辑文字不会改变画像分节。');
  const source = editSource(state, text, context);
  const memory = newMemory(state, context.newId('edit-fact'), text, source, context);
  Object.assign(item, {
    text,
    revision: item.revision + 1,
    updatedAt: context.at,
    sourceIds: [source.id],
    factIds: [memory.id],
    sourceRefs: memory.sourceRefs,
    userEdited: true,
  });
  return { item, memory, source };
}
function invalidateProfiles(state: AboutMeState, factIds: string[], context: ModelContext) {
  const affected = state.profileItems.filter(
    (item) => item.status === 'active' && item.factIds.some((id) => factIds.includes(id)),
  );
  for (const item of affected)
    Object.assign(item, {
      text: '',
      sourceRefs: [],
      sourceIds: [],
      factIds: [],
      status: 'deleted',
      revision: item.revision + 1,
      updatedAt: context.at,
    });
  return affected.map((item) => item.id);
}
function memoryEdit(
  state: AboutMeState,
  command: Extract<AboutMeCommand, { type: 'memory-edit' }>,
  context: ModelContext,
) {
  const item = target(state.memories, command);
  if (item.status !== 'active') throw new AboutMeError('CONFLICT', 409, '这条记忆已停用，不能直接更正。');
  const text = safeText(command.text),
    source = editSource(state, text, context);
  const profiles = invalidateProfiles(state, [item.id], context);
  Object.assign(item, {
    text,
    sourceRefs: [sourceRef(source, text)],
    revision: item.revision + 1,
    updatedAt: context.at,
  });
  return { item, source, profiles };
}
function proposalAct(
  state: AboutMeState,
  command: Extract<AboutMeCommand, { type: 'proposal-act' }>,
  context: ModelContext,
): { item: ProposalItem; memory?: MemoryItem } {
  const item = target(state.proposals, command);
  if (item.status !== 'pending') throw new AboutMeError('CONFLICT', 409, '这条提案已变化，请重新查看。');
  if (!['remember', 'dismiss', 'remember-category'].includes(command.action))
    throw new AboutMeError('INVALID', 422, '请选择有效的确认操作。');
  if (command.action === 'remember-category' && !item.category)
    throw new AboutMeError('INVALID', 422, '此条没有明确类别，不能保存同类偏好。');
  if (command.action === 'dismiss') {
    Object.assign(item, { status: 'dismissed', revision: item.revision + 1, updatedAt: context.at });
    return { item };
  }
  let refs = item.sourceRefs;
  if (item.kind === 'legacy-note') {
    const source = editSource(state, safeText(item.text), context);
    refs = [sourceRef(source, item.text)];
  } else if (!refs.length || refs.some((ref) => !projectSource(state, ref).available))
    throw new AboutMeError('CONFLICT', 409, '提案的授权来源已不可用，请重新核对。');
  const id = `local-fact-${item.id}`;
  if (state.revokedFactIds.includes(id) || state.memories.some((fact) => fact.id === id))
    throw new AboutMeError('CONFLICT', 409, '已撤回或已处理的事实不能从旧提案复活。');
  const memory: MemoryItem = {
    id,
    text: safeText(item.text),
    category: item.category,
    proposalId: item.id,
    revision: item.revision + 1,
    status: 'active',
    sourceRefs: refs,
    createdAt: context.at,
    updatedAt: context.at,
    categorySaved: command.action === 'remember-category',
  };
  state.memories.push(memory);
  Object.assign(item, {
    factId: id,
    sourceRefs: refs,
    status: 'saved',
    revision: item.revision + 1,
    updatedAt: context.at,
    categorySaved: memory.categorySaved,
  });
  if (memory.categorySaved && item.category && !state.autoSaveCategories.includes(item.category))
    state.autoSaveCategories.push(item.category);
  return { item, memory };
}
function memoryDelete(
  state: AboutMeState,
  command: Extract<AboutMeCommand, { type: 'memory-delete' }>,
  context: ModelContext,
) {
  const item = target(state.memories, command);
  if (state.revision !== command.expectedSnapshotRevision)
    throw new AboutMeError('CONFLICT', 409, '删除范围已变化，请重新预览并二次确认。');
  const preview = previewDeletion(state, item.id, command.scope, command.sourceRef);
  for (const fact of state.memories.filter((row) => preview.affectedFactIds.includes(row.id))) {
    Object.assign(fact, {
      text: '',
      sourceRefs: [],
      status: 'deleted',
      revision: fact.revision + 1,
      updatedAt: context.at,
    });
    if (!state.revokedFactIds.includes(fact.id)) state.revokedFactIds.push(fact.id);
  }
  const profiles = invalidateProfiles(state, preview.affectedFactIds, context);
  for (const profile of state.profileItems.filter(
    (row) => preview.affectedProfileIds.includes(row.id) && row.status === 'active',
  )) {
    Object.assign(profile, {
      text: '',
      sourceRefs: [],
      sourceIds: [],
      factIds: [],
      status: 'deleted',
      revision: profile.revision + 1,
      updatedAt: context.at,
    });
    profiles.push(profile.id);
  }
  for (const proposal of state.proposals.filter((row) => preview.affectedProposalIds.includes(row.id)))
    Object.assign(proposal, {
      text: '',
      sourceRefs: [],
      status: 'deleted',
      revision: proposal.revision + 1,
      updatedAt: context.at,
    });
  for (const symbol of state.dictionary.filter((row) => preview.affectedSymbolIds.includes(row.id)))
    Object.assign(symbol, { text: '', sourceRefs: [], status: 'deleted', revision: symbol.revision + 1 });
  if (preview.sourceRef) {
    const source = state.sources.find((row) => row.id === preview.sourceRef!.messageId)!;
    Object.assign(source, { content: '', status: 'deleted', revision: source.revision + 1 });
  }
  return {
    item,
    affectedIds: [
      ...preview.affectedFactIds,
      ...new Set(profiles),
      ...preview.affectedProposalIds,
      ...preview.affectedSymbolIds,
    ],
  };
}

export function applyAboutMeCommand(
  current: AboutMeState,
  command: AboutMeCommand,
  context: ModelContext,
): { state: AboutMeState; receipt: AboutMeReceipt } {
  if (
    !command.requestId?.trim() ||
    !command.id?.trim() ||
    !Number.isInteger(command.expectedRevision) ||
    command.expectedRevision < 0
  )
    throw new AboutMeError('INVALID', 422, '提交需要稳定操作编号与有效版本。');
  const state = structuredClone(current);
  const result: AboutMeReceipt = {
    requestId: command.requestId,
    kind: command.type,
    id: command.id,
    revision: 0,
    snapshotRevision: state.revision + 1,
    write_status: 'saved',
    affectedIds: [command.id],
  };
  switch (command.type) {
    case 'profile-edit': {
      const edited = profileEdit(state, command, context);
      Object.assign(result, { revision: edited.item.revision, factId: edited.memory.id, sourceId: edited.source.id });
      break;
    }
    case 'profile-delete': {
      const item = target(state.profileItems, command);
      Object.assign(item, {
        text: '',
        sourceRefs: [],
        sourceIds: [],
        factIds: [],
        status: 'deleted',
        revision: item.revision + 1,
        updatedAt: context.at,
      });
      Object.assign(result, { revision: item.revision, write_status: 'deleted' });
      break;
    }
    case 'memory-edit': {
      const edited = memoryEdit(state, command, context);
      Object.assign(result, {
        revision: edited.item.revision,
        factId: edited.item.id,
        sourceId: edited.source.id,
        affectedIds: [edited.item.id, ...edited.profiles],
      });
      break;
    }
    case 'memory-stop': {
      const item = target(state.memories, command);
      if (item.status !== 'active') throw new AboutMeError('CONFLICT', 409, '这条记忆已变化，请重新查看。');
      Object.assign(item, { status: 'stopped', revision: item.revision + 1, updatedAt: context.at });
      const profiles = invalidateProfiles(state, [item.id], context);
      Object.assign(result, {
        revision: item.revision,
        factId: item.id,
        write_status: 'stopped',
        affectedIds: [item.id, ...profiles],
      });
      break;
    }
    case 'memory-delete': {
      const deleted = memoryDelete(state, command, context);
      Object.assign(result, {
        revision: deleted.item.revision,
        factId: deleted.item.id,
        write_status: 'deleted',
        affectedIds: deleted.affectedIds,
      });
      break;
    }
    case 'proposal-act': {
      const acted = proposalAct(state, command, context);
      Object.assign(result, {
        revision: acted.item.revision,
        factId: acted.memory?.id,
        write_status: acted.memory ? 'saved' : 'dismissed',
        affectedIds: [acted.item.id, ...(acted.memory ? [acted.memory.id] : [])],
      });
      break;
    }
    case 'symbol-delete': {
      const item = target(state.dictionary, command);
      Object.assign(item, { status: 'deleted', text: '', sourceRefs: [], revision: item.revision + 1 });
      Object.assign(result, { revision: item.revision, write_status: 'deleted' });
      break;
    }
    default:
      throw new AboutMeError('INVALID', 422, '没有对应的本地操作。');
  }
  state.revision++;
  if (result.factId || command.type === 'proposal-act')
    result.memoryReceipt = currentMemoryReceipts(state).find((row) =>
      result.factId ? row.fact_id === result.factId : row.proposal_id === command.id,
    );
  return { state, receipt: result };
}

export function validateAboutMeSeed(state: AboutMeState) {
  for (const text of [...state.profileItems, ...state.memories, ...state.proposals, ...state.dictionary]
    .map((item) => item.text)
    .filter(Boolean))
    safeText(text);
  for (const source of state.sources) safeText(source.content);
  for (const item of [...state.profileItems, ...state.memories, ...state.proposals, ...state.dictionary])
    for (const ref of item.sourceRefs) {
      const source = state.sources.find((candidate) => candidate.id === ref.messageId);
      if (
        !source ||
        source.revision !== ref.version ||
        Array.from(source.content).slice(ref.start, ref.end).join('') !== ref.quote
      )
        throw new AboutMeError('INVALID', 422, '合成引用必须与来源版本及连续原话一致。');
    }
}
