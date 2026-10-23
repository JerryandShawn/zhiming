import {
  OrganizeError,
  type AppliedField,
  type FieldChange,
  type FieldKey,
  type FieldValue,
  type Json,
  type OrganizeDocument,
  type OrganizeSeed,
  type RevertConflict,
  type WireChangeSet,
} from './types';
import {
  active,
  canonical,
  fieldId,
  immutableRecord,
  LABEL_FIELDS,
  readField,
  same,
  validateDocument,
  writeField,
} from './values';

export async function buildChanges(
  seed: OrganizeSeed,
  digest: (text: string) => Promise<string>,
): Promise<WireChangeSet | null> {
  const accepted = seed.segments.filter((item) => item.decision === 'accepted');
  if (!accepted.length) return null;
  const target = structuredClone(seed.document);
  for (const topic of seed.topics) {
    const rows = accepted.filter((item) => item.topic_id === topic.id),
      ids = rows.flatMap((item) => item.message_ids);
    if (!ids.length) continue;
    target.topics[topic.id] = {
      id: topic.id,
      owner_id: target.owner_id,
      subject_id: target.subject_id,
      title: topic.title,
      space_id: topic.space_id,
      status: 'open',
      message_ids: ids,
    };
    for (const id of ids)
      Object.assign(target.messages[id], {
        space_id: topic.space_id,
        topic_id: topic.id,
        space_secondary: null,
        route_source: 'user',
        route_confidence: 1,
      });
  }
  const ops: FieldChange[] = [];
  for (const id of Object.keys(target.messages).sort())
    for (const field of [...LABEL_FIELDS].sort()) {
      const key = { collection: 'messages' as const, entity_id: id, field };
      const before = readField(seed.document, key),
        after = readField(target, key);
      if (!same(before, after)) ops.push({ ...key, before, after });
    }
  for (const id of Object.keys(target.topics).sort())
    if (!Object.hasOwn(seed.document.topics, id)) {
      ops.push({
        collection: 'topics',
        entity_id: id,
        field: null,
        before: { present: false },
        after: { present: true, value: structuredClone(target.topics[id]) as unknown as Json },
      });
    }
  const ids = new Set(accepted.flatMap((item) => item.message_ids)),
    topicIds = new Set<string>();
  for (const id of ids) {
    const original = seed.document.messages[id].topic_id;
    if (original) topicIds.add(original);
  }
  const guards = await Promise.all(
    (['messages', 'topics'] as const).flatMap((collection) =>
      [...(collection === 'messages' ? ids : topicIds)].sort().map(async (entity_id) => {
        active(seed.document[collection][entity_id]);
        const immutable_digest = await digest(canonical(immutableRecord(seed.document, collection, entity_id)));
        if (!/^[a-f0-9]{64}$/.test(immutable_digest)) throw new OrganizeError('UNAVAILABLE', '来源核对摘要无效。');
        return { collection, entity_id, immutable_digest };
      }),
    ),
  );
  return {
    batch_id: seed.batch_id,
    owner_id: target.owner_id,
    subject_id: target.subject_id,
    ops,
    inverse_ops: [...ops].reverse().map((op) => ({ ...op, before: op.after, after: op.before })),
    source_guards: guards,
  };
}

export async function checkSources(
  document: OrganizeDocument,
  changes: WireChangeSet,
  digest: (text: string) => Promise<string>,
) {
  validateDocument(document, changes.owner_id, changes.subject_id);
  for (const guard of changes.source_guards) {
    const row = document[guard.collection][guard.entity_id];
    if (!row) throw new OrganizeError('SOURCE_CHANGED', '整理来源已不存在，请重新核对。');
    active(row);
    if (
      (await digest(canonical(immutableRecord(document, guard.collection, guard.entity_id)))) !== guard.immutable_digest
    )
      throw new OrganizeError('SOURCE_CHANGED', '整理来源的原文或修订已变化，未修改任何数据。');
  }
  for (const op of changes.ops)
    if (op.collection === 'topics' && Object.hasOwn(document.topics, op.entity_id))
      active(document.topics[op.entity_id]);
}
export function applyChanges(document: OrganizeDocument, changes: WireChangeSet): OrganizeDocument {
  if (changes.ops.some((op) => !same(readField(document, op), op.before)))
    throw new OrganizeError('CONFLICT', '整理前置标签已变化，整批未应用。');
  const candidate = structuredClone(document);
  for (const op of changes.ops) writeField(candidate, op, op.after);
  validateDocument(candidate, changes.owner_id, changes.subject_id);
  return candidate;
}
export function appliedFields(changes: WireChangeSet, seed: OrganizeSeed): AppliedField[] {
  const titles = new Map(
    changes.ops.flatMap((op) => {
      const value = op.after.present ? op.after.value : null;
      return op.collection === 'topics' &&
        op.field === null &&
        value &&
        typeof value === 'object' &&
        !Array.isArray(value) &&
        typeof value.title === 'string'
        ? [[op.entity_id, value.title] as const]
        : [];
    }),
  );
  const messageTopics = new Map(
    changes.ops.flatMap((op) =>
      op.collection === 'messages' && op.field === 'topic_id' && op.after.present && typeof op.after.value === 'string'
        ? [[op.entity_id, op.after.value] as const]
        : [],
    ),
  );
  return changes.ops.map((op) => {
    const segmentIndex = seed.segments.findIndex((item) => item.message_ids.includes(op.entity_id));
    const messageIndex = seed.segments[segmentIndex]?.message_ids.indexOf(op.entity_id) ?? -1;
    const subject =
      titles.get(op.collection === 'topics' ? op.entity_id : (messageTopics.get(op.entity_id) ?? '')) ?? '已审阅片段';
    return {
      ...structuredClone(op),
      state: 'applied',
      group_id: canonical([op.collection, op.entity_id]),
      label:
        op.field === null
          ? `${subject} · 新建话题`
          : `${subject} · 片段${segmentIndex + 1}第${messageIndex + 1}条 · 归区与话题标签`,
    };
  });
}
function conflict(changes: WireChangeSet, key: FieldKey, reason: RevertConflict['reason']): RevertConflict {
  return { batch_id: changes.batch_id, collection: key.collection, entity_id: key.entity_id, field: key.field, reason };
}
export function revertFields(
  document: OrganizeDocument,
  changes: WireChangeSet,
  fields: AppliedField[],
  selected?: FieldKey[],
) {
  const scope = new Set((selected ?? fields.filter((item) => item.state === 'applied')).map(fieldId));
  const candidate = structuredClone(document),
    next = structuredClone(fields),
    conflicts: RevertConflict[] = [];
  // The mock UI exposes each message's routing labels as one explicit group.
  // Preserve that group when any selected member changed, so a safe neighbour can still undo.
  const blockedMessages = new Set(
    next
      .filter(
        (field) =>
          field.collection === 'messages' &&
          field.state === 'applied' &&
          scope.has(fieldId(field)) &&
          !same(readField(document, field), field.after),
      )
      .map((field) => field.entity_id),
  );
  for (const op of changes.inverse_ops) {
    const key = fieldId(op),
      field = next.find((item) => fieldId(item) === key);
    if (!field || field.state !== 'applied' || !scope.has(key)) continue;
    if (op.collection === 'messages' && blockedMessages.has(op.entity_id)) {
      conflicts.push(conflict(changes, op, 'field_changed'));
      field.state = 'conflict';
    } else if (same(readField(candidate, op), op.before)) {
      writeField(candidate, op, op.after);
      field.state = 'reverted';
    } else {
      conflicts.push(conflict(changes, op, 'field_changed'));
      field.state = 'conflict';
    }
  }
  for (const field of next)
    if (
      field.collection === 'topics' &&
      field.field === null &&
      field.state === 'reverted' &&
      Object.values(candidate.messages).some((item) => item.topic_id === field.entity_id)
    ) {
      const original = readField(document, field);
      writeField(candidate, field, original);
      field.state = 'conflict';
      conflicts.push(conflict(changes, field, 'later_references'));
    }
  validateDocument(candidate, changes.owner_id, changes.subject_id);
  return { document: candidate, fields: next, conflicts };
}
export function fieldValuesForDisplay(value: FieldValue): string {
  if (!value.present) return '未设置';
  if (value.value === null) return '空值';
  return typeof value.value === 'string' ? value.value : canonical(value.value);
}
