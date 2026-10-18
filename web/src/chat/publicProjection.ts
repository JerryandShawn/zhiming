import type { HistoryRow } from './types';

const birthField = /\bbirth\.[a-z_]+(?:\.[a-z_]+)*/i;
const profileAction = /请保存我已核对并确认的出生与性别资料/;
export const hiddenProfile = '已核对出生资料，原值请到资料页查看';
export function hasBirthFields(text: string) {
  return birthField.test(text);
}
export function publicChatText(text: string): string {
  if (profileAction.test(text)) return hiddenProfile;
  return text
    .split('\n')
    .map((line) => (hasBirthFields(line) ? hiddenProfile : line))
    .join('\n');
}
export function publicHistoryText(row: HistoryRow): string {
  // Profile confirmation commands are program records, not ordinary dialogue.
  if (row.source === 'web-action' && (profileAction.test(row.content) || hasBirthFields(row.content)))
    return hiddenProfile;
  return publicChatText(row.content);
}
