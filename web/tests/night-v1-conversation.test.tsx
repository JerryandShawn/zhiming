import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { createNightPort } from '../src/night/port';
import { useNormalConversation } from '../src/night/useNormalConversation';
import type { AskAnswerContext, AskAnswerReceipt } from '../src/chat/interactions/contracts';

vi.mock('../src/night/events', async (importOriginal) => {
  const real = await importOriginal<typeof import('../src/night/events')>();
  return {
    ...real,
    // Replay the real wire frames and parser without presentation pauses or a host-dependent clock.
    playDemo: (...args: Parameters<typeof real.playDemo>) => {
      const [scenario, accept, signal, , context] = args;
      return real.playDemo(scenario, accept, signal, 0, {
        ...context,
        now: () => new Date('2026-10-20T23:00:00+08:00'),
      });
    },
  };
});

async function ready() {
  const port = createNightPort();
  const hook = renderHook(() => useNormalConversation(port, true));
  await waitFor(() => expect(hook.result.current.state.complete).toBe(true));
  const question = hook.result.current.state.question!;
  expect(question.askId).toBe('local-ask');
  expect(question.optionIds?.[0]).toBe('trial');
  return { ...hook, port };
}

const context: AskAnswerContext = { askId: 'local-ask', optionIds: ['trial'] };
const answer = '先做个小试验';
const draft = '还没发送的合成草稿，确认失败时应保留。';

describe('v1 parent conversation acknowledgement boundary', () => {
  it.each(['askId', 'optionIds', 'answer'] as const)(
    'does not commit parent state after an acknowledgement with a wrong %s',
    async (mismatch) => {
      const { result, port } = await ready();
      const submit = vi.spyOn(port, 'answer').mockImplementation(async (text, requestId, source) => ({
        status: 'accepted',
        answer: mismatch === 'answer' ? '另一段合成回答' : text,
        request_id: requestId,
        askId: mismatch === 'askId' ? 'another-ask' : source?.askId,
        optionIds: mismatch === 'optionIds' ? ['clarify'] : source?.optionIds,
      }));
      act(() => result.current.setDraft(draft));
      await act(async () => {
        await expect(result.current.answer(answer, context)).rejects.toThrow('尚未收到当前提问的有效确认');
      });
      expect(submit).toHaveBeenCalledExactlyOnceWith(answer, expect.any(String), context);
      expect(result.current.answered).toBe('');
      expect(result.current.answeredOptionIds).toBeUndefined();
      expect(result.current.draft).toBe(draft);
      expect(result.current.reply).toBe('');
    },
  );

  it('commits a valid scoped acknowledgement only after the isolated port accepts it', async () => {
    const { result, port } = await ready();
    const submit = vi.spyOn(port, 'answer');
    act(() => result.current.setDraft(draft));
    await act(async () => {
      const receipt = await result.current.answer(answer, context);
      expect(receipt.askId).toBe(context.askId);
      expect(receipt.optionIds).toEqual(context.optionIds);
    });
    expect(submit).toHaveBeenCalledExactlyOnceWith(answer, expect.any(String), context);
    expect(result.current.answered).toBe(answer);
    expect(result.current.answeredOptionIds).toEqual(['trial']);
    expect(result.current.draft).toBe('');
    expect(result.current.reply).toContain('已收到你的选择');
  });

  it('ignores a late acknowledgement after a new episode starts even when the ask ID is reused', async () => {
    const { result, port } = await ready();
    let resolve: (receipt: AskAnswerReceipt) => void = () => undefined;
    vi.spyOn(port, 'answer').mockImplementationOnce(
      () =>
        new Promise<AskAnswerReceipt>((done) => {
          resolve = done;
        }),
    );
    let rejection: unknown;
    const pending = result.current.answer(answer, context).catch((reason: unknown) => {
      rejection = reason;
    });
    act(() => result.current.replay('cards'));
    await waitFor(() => {
      expect(result.current.round).toBe(1);
      expect(result.current.state.complete).toBe(true);
    });
    expect(result.current.state.question?.askId).toBe(context.askId);
    act(() => result.current.setDraft('下一轮新写的合成草稿'));
    await act(async () => {
      resolve({ status: 'accepted', answer, request_id: 'synthetic-late', ...context });
      await pending;
    });
    expect(rejection).toBeInstanceOf(DOMException);
    expect(rejection).toMatchObject({ name: 'AbortError' });
    expect(result.current.answered).toBe('');
    expect(result.current.answeredOptionIds).toBeUndefined();
    expect(result.current.draft).toBe('下一轮新写的合成草稿');
    expect(result.current.reply).toBe('');
  });
});
