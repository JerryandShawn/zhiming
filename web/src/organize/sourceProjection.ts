import type { OrganizeDocument, OrganizeSeed } from './types';
import { active, immutableRecord, same } from './values';

export const STOPPED_SOURCE_MESSAGE = '来源已停止使用，请重新整理';

function usable(seed: OrganizeSeed, current: OrganizeDocument, messageId: string) {
  try {
    const original = seed.document.messages[messageId],
      message = current.messages[messageId];
    if (!original || !message) return false;
    active(message);
    if (!same(immutableRecord(seed.document, 'messages', messageId), immutableRecord(current, 'messages', messageId)))
      return false;
    if (original.topic_id) {
      const topic = current.topics[original.topic_id];
      if (!topic) return false;
      active(topic);
      if (
        !same(
          immutableRecord(seed.document, 'topics', original.topic_id),
          immutableRecord(current, 'topics', original.topic_id),
        )
      )
        return false;
    }
    if (message.topic_id) active(current.topics[message.topic_id]);
    return true;
  } catch {
    return false;
  }
}

/** A withdrawn segment stops being a display source; the ledger retains its immutable proof. */
export function projectOrganizeSources(seed: OrganizeSeed, current: OrganizeDocument) {
  const document = structuredClone(current);
  const segments = seed.segments.map((segment) => {
    const source_available = segment.message_ids.every((id) => usable(seed, current, id));
    if (!source_available)
      for (const id of segment.message_ids)
        if (Object.hasOwn(document.messages, id)) document.messages[id].content = '';
    return { ...segment, source_available, sample: source_available ? segment.sample : STOPPED_SOURCE_MESSAGE };
  });
  return { document, segments };
}
