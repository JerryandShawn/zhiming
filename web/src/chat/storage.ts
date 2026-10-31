import { object, string, type ChatPayload, type PendingChat } from './types';
import { operationNamespace } from '../api/client';
const key = (namespace = operationNamespace()) => `mingjing-chat-pending-v1:${namespace}`;
export function loadPending(namespace = operationNamespace()): PendingChat | undefined {
  try {
    const data = object(JSON.parse(sessionStorage.getItem(key(namespace)) || 'null')),
      payload = object(data.payload);
    if (
      !string(payload.request_id) ||
      !string(payload.message) ||
      !Array.isArray(payload.images) ||
      !payload.images.every((image) => typeof image === 'string') ||
      (data.namespace && data.namespace !== namespace)
    )
      return;
    return { ...(data as PendingChat), namespace };
  } catch {
    return;
  }
}
export function isCurrentChat(pending: PendingChat) {
  return (
    pending.namespace === operationNamespace() &&
    loadPending(pending.namespace)?.payload.request_id === pending.payload.request_id
  );
}
export function assertCurrentChat(pending: PendingChat, signal?: AbortSignal) {
  signal?.throwIfAborted();
  if (!isCurrentChat(pending)) throw new DOMException('登录或对话记录已切换', 'AbortError');
}
export function storePending(pending: PendingChat, creating = false) {
  if (pending.namespace !== operationNamespace() || (!creating && !isCurrentChat(pending)))
    throw new DOMException('登录或对话记录已切换', 'AbortError');
  try {
    sessionStorage.setItem(key(pending.namespace), JSON.stringify(pending));
  } catch {
    throw new Error('本机无法保留重试记录，请减少附件或开启会话存储后再发送');
  }
}
export function clearPending(pending: PendingChat) {
  if (!isCurrentChat(pending)) return false;
  sessionStorage.removeItem(key(pending.namespace));
  return true;
}
export function newPending(
  message: string,
  images: string[],
  session = 'shared',
  namespace = operationNamespace(),
): PendingChat {
  const payload: ChatPayload = {
    request_id: crypto.randomUUID(),
    message,
    images,
    session_id: session,
    case_ids: [],
    depth: 'standard',
  };
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  const caseId = params.get('case');
  if (caseId) payload.case_ids = [caseId];
  const drawId = params.get('draw');
  if (drawId) payload.draw_id = drawId;
  const date = params.get('date'),
    system = params.get('system'),
    focus = params.get('focus'),
    field = params.get('key');
  if (date || system || focus || field) {
    const selection: NonNullable<ChatPayload['selection']> = {};
    if (date) {
      if (
        !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
        Number.isNaN(new Date(date).getTime()) ||
        new Date(date).toISOString().slice(0, 10) !== date
      )
        throw new Error('所选日期无效，请回到命盘页重新选择');
      selection.date = date;
    }
    if (system && ['bazi', 'ziwei', 'astro'].includes(system)) {
      selection.system = system;
      selection.systems = [system];
    }
    if (focus) selection.focus = focus;
    if (field) selection.key = field;
    payload.selection = selection;
  }
  const pending = { payload, runId: payload.request_id, namespace };
  storePending(pending, true);
  return pending;
}
export function readDraft() {
  try {
    return sessionStorage.getItem(`${key()}:draft`) || '';
  } catch {
    return '';
  }
}
export function saveDraft(text: string, namespace = operationNamespace()) {
  if (namespace !== operationNamespace()) return;
  try {
    sessionStorage.setItem(`${key(namespace)}:draft`, text);
  } catch {
    /* Sending verifies durable request storage separately. */
  }
}
