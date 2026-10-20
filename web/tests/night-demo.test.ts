import { describe, expect, it } from 'vitest';
import { initialStream } from '../src/chat/types';
import { reduceChat } from '../src/chat/reducer';
import { demoSteps, playDemo } from '../src/night/events';
import { createNightPort } from '../src/night/port';

describe('夜间模拟接线层', () => {
  it('字节流经正式解码，覆盖冻结v1的十二类事件', async () => {
    const seen = new Set<string>();
    let state = initialStream();
    await playDemo(
      'cards',
      (event) => {
        seen.add(event.type);
        state = reduceChat(state, event);
      },
      new AbortController().signal,
      0,
    );
    expect(state.complete).toBe(true);
    expect(state.question?.options).toHaveLength(2);
    expect(state.decisions).toHaveLength(2);
    expect(state.receipts).toHaveLength(2);
    expect(state.text).toContain('可验证的小步骤');
    await playDemo(
      'review',
      (event) => {
        seen.add(event.type);
        state = reduceChat(state, event);
      },
      new AbortController().signal,
      0,
    );
    expect(state.revised).toBe(true);
    expect(state.text).not.toContain('所有安排定下来');
    await playDemo(
      'error',
      (event) => {
        seen.add(event.type);
      },
      new AbortController().signal,
      0,
    );
    expect([...seen].sort()).toEqual(
      [
        'started',
        'status',
        'tool_call',
        'tool_result',
        'text_delta',
        'text_reset',
        'memory_receipt',
        'ask_user',
        'final',
        'error',
        'present_options',
        'review',
      ].sort(),
    );
  });
  it('旧恢复替换不误报修订；终止后不再接收事件', async () => {
    let state = initialStream();
    await playDemo(
      'resumed',
      (event) => {
        state = reduceChat(state, event);
      },
      new AbortController().signal,
      0,
    );
    expect(state.text).not.toContain('旧片段');
    expect(state.revised).toBe(false);
    const abort = new AbortController();
    abort.abort();
    await expect(
      playDemo(
        'cards',
        () => {
          throw new Error('不应收到事件');
        },
        abort.signal,
        0,
      ),
    ).rejects.toHaveProperty('name', 'AbortError');
  });
  it('提问确认幂等，拒绝同一请求被改为另一答案', async () => {
    const port = createNightPort();
    const result = await port.answer(' 先试试看 ', 'answer-1');
    expect(result).toEqual({ status: 'accepted', answer: '先试试看', request_id: 'answer-1' });
    expect(await port.answer('先试试看', 'answer-1')).toBe(result);
    await expect(port.answer('换一个', 'answer-1')).rejects.toThrow('已经回答');
    await expect(port.answer('', 'answer-2')).rejects.toThrow('先说说');
  });
  it('记忆回执只提交一次，拒绝过时的其他写操作', async () => {
    const port = createNightPort();
    const item = {
      proposal_id: 'local-proposal',
      write_status: 'pending_confirmation',
      summary: '希望跟进一项健康安排（合成示例）',
      revision: 1,
    };
    const saved = await port.memory.execute('remember', item);
    expect(saved.write_status).toBe('saved');
    expect(await port.memory.execute('remember', item)).toBe(saved);
    await expect(port.memory.execute('dismiss', item)).rejects.toThrow('已变化');
    const undone = await port.memory.execute('undo', { ...item, ...saved, summary: item.summary });
    expect(undone.write_status).toBe('stopped');
    expect(port.memory.supports('undo', { ...item, write_status: 'stopped' })).toBe(false);
  });
  it('同类自动记只在有效类别回执后更新本地偏好', async () => {
    const port = createNightPort();
    const item = {
      proposal_id: 'local-proposal',
      write_status: 'pending_confirmation',
      summary: '希望跟进一项健康安排（合成示例）',
      revision: 1,
    };
    expect(port.memory.supports('remember-category', item)).toBe(false);
    await expect(port.memory.execute('remember-category', item)).rejects.toThrow();
    expect(port.autoSaveCategories.size).toBe(0);
    const result = await port.memory.execute('remember-category', { ...item, category: 'health' });
    expect(result.category_saved).toBe(true);
    expect(result.category).toBe('health');
    expect([...port.autoSaveCategories]).toEqual(['health']);
    await expect(port.memory.execute('remember-category', { ...item, category: 'finance' })).rejects.toThrow(
      '内容已经改变',
    );
    await expect(
      port.memory.execute('remember-category', { ...item, category: 'health', summary: '换了正文' }),
    ).rejects.toThrow('内容已经改变');
  });
  it('所有片段仅使用公开合成内容，不包含登录与真实模型接线', () => {
    for (const scenario of ['cards', 'review', 'error', 'resumed'] as const) {
      const data = JSON.stringify(demoSteps(scenario));
      expect(data).not.toMatch(/api_key|https?:|birth_date|birth_time|birth_place|access_token/i);
    }
  });
});
