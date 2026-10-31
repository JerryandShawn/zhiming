import { validAskAnswerReceipt, type AskAnswerContext } from '../chat/interactions/contracts';
import type { Question } from '../chat/types';
import type { NightPort } from './port';

export async function acceptQuestionAnswer(
  port: NightPort,
  question: Question | undefined,
  text: string,
  context: AskAnswerContext | undefined,
  requestId: string,
  isCurrent: () => boolean,
) {
  const answer = text.trim();
  if (!answer) throw new Error('先说说你的想法。');
  const source = question?.askId ? (context ?? { askId: question.askId, optionIds: [] }) : context;
  if (question?.askId) {
    if (source?.askId !== question.askId || new Set(source.optionIds).size !== source.optionIds.length)
      throw new Error('这张提问卡已变化，请重新选择。');
    const ids = question.optionIds ?? [];
    if (source.optionIds.some((id) => !ids.includes(id)) || (!question.multi && source.optionIds.length > 1))
      throw new Error('这次选择不属于当前提问。');
    const selected = ids.flatMap((id, index) => (source.optionIds.includes(id) ? [question.options[index]] : []));
    if (selected.length ? selected.join('；') !== answer : !question.allow_free_text)
      throw new Error('请重新核对这次选择。');
  }
  const receipt = await port.answer(answer, requestId, source);
  if (!isCurrent()) throw new DOMException('这一轮已切换', 'AbortError');
  if (receipt.request_id !== requestId || !validAskAnswerReceipt(receipt, answer, source))
    throw new Error('尚未收到当前提问的有效确认。');
  return receipt;
}
