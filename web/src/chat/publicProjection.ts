import type { HistoryRow } from './types';

const birthField =
  /\bbirth\.[a-z_]+(?:\.[a-z_]+)*|["']?\bbirth["']?\s*:|\b(?:birth_raw|raw_birth|declared_birth|solar_datetime|corrected_time|civil_time|utc_time|birth_date|birth_time|birth_location)\b|(?:出生日期|出生时间|出生时刻|出生地点|出生时区)\s*[:：=]\s*\S/i;
const profileAction = /请保存我已核对并确认的出生与性别资料/;
export const hiddenProfile = '已核对出生资料，原值请到资料页查看';
export function hasBirthFields(text: string) {
  return birthField.test(text);
}
export function publicChatText(text: string): string {
  // A structured value can span lines or network chunks. Hide its entire text
  // projection so a following line cannot reveal a value whose key was removed.
  return profileAction.test(text) || hasBirthFields(text) ? hiddenProfile : text;
}
export function publicHistoryText(row: HistoryRow): string {
  // Profile confirmation commands are program records, not ordinary dialogue.
  if (row.source === 'web-action' && (profileAction.test(row.content) || hasBirthFields(row.content)))
    return hiddenProfile;
  return publicChatText(row.content);
}
