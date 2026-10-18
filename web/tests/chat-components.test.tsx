import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Answer, HistoryMessage } from '../src/chat/Answers';
import { initialStream } from '../src/chat/types';
import Chat from '../src/live/Chat';
import { loadPending } from '../src/chat/storage';
import { useAuth } from '../src/api/client';
import { useChat } from '../src/chat/useChat';

afterEach(() => vi.unstubAllGlobals());
describe('live chat rendering', () => {
  it('never promotes model prose into a memory receipt', () => {
    render(<Answer state={{ ...initialStream(), text: '我已经记下了这件事。' }} />);
    expect(screen.getByText('我已经记下了这件事。')).toBeVisible();
    expect(screen.queryByText(/程序回执/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '撤销使用' })).not.toBeInTheDocument();
  });
  it('renders revised, tool, question, decision and program receipt states', async () => {
    const reply = vi.fn();
    render(
      <Answer
        onReply={reply}
        state={{
          ...initialStream(),
          text: '已核对的回答',
          revised: true,
          tools: [{ name: 'calendar', summary: '已核对日期', done: true }],
          question: { question: '技术面还是终面？', options: ['技术面'], allow_free_text: true, why: '准备重点不同' },
          decisions: [
            {
              option: '先准备',
              benefit: '更充分',
              cost: '时间',
              risk: '等待',
              reversibility: '可改',
              first_step: '列清单',
            },
          ],
          receipts: [{ fact_id: 'synthetic', write_status: 'pending_confirmation', summary: '待授权' }],
        }}
      />,
    );
    expect(screen.getByText('已修订')).toBeVisible();
    expect(screen.getByText(/尚未保存为有效记忆/)).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '技术面' }));
    expect(reply).toHaveBeenCalledWith('技术面');
    for (const label of ['收益', '代价', '风险', '可逆性', '第一步']) expect(screen.getByText(label)).toBeVisible();
  });
  it('only confirms undo after a program receipt, and preserves the operation on invalid receipt', async () => {
    const bodies: string[] = [];
    const fetcher = vi.fn(async (_path: unknown, init?: RequestInit) => {
      bodies.push(String(init?.body));
      return Response.json(bodies.length === 1 ? { status: 'unknown' } : { write_status: 'stopped' });
    });
    vi.stubGlobal('fetch', fetcher);
    render(
      <Answer
        state={{
          ...initialStream(),
          receipts: [{ fact_id: 'synthetic-undo', revision: 1, write_status: 'saved', summary: '合成偏好' }],
        }}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: '撤销使用' }));
    expect(screen.queryByText('已撤销，不会再提起')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '撤销使用' }));
    await screen.findByText('已撤销，不会再提起');
    expect(JSON.parse(bodies[0]).request_id).toBe(JSON.parse(bodies[1]).request_id);
  });
  it('connects v3 chat and keeps the question plus final answer after success', async () => {
    sessionStorage.clear();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string) =>
        path.startsWith('/api/history')
          ? Response.json([])
          : new Response(
              'data: {"type":"started","run_id":"synthetic-run"}\n\ndata: {"type":"result","result":{"answer":"合成回答"}}\n\ndata: [DONE]\n\n',
            ),
      ),
    );
    const query = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={query}>
        <Chat />
      </QueryClientProvider>,
    );
    await userEvent.type(screen.getByRole('textbox', { name: '和明镜说说' }), '合成问题');
    await userEvent.click(screen.getByRole('button', { name: '发送' }));
    await screen.findByText('合成回答');
    expect(screen.getByText('合成问题')).toBeVisible();
    await waitFor(() => expect(loadPending()).toBeUndefined());
    expect(screen.getByRole('switch', { name: '无痕模式' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: '和明镜说说' })).toHaveValue('');
  });
  it('keeps assistant history timestamps and Feishu provenance visible', () => {
    render(
      <HistoryMessage
        row={{
          role: 'assistant',
          at: '2026-10-18T01:15:00Z',
          content: '合成历史',
          source: 'feishu',
          cursor: 'synthetic-cursor',
          turn_id: 'synthetic-turn',
        }}
        restore={() => undefined}
      />,
    );
    expect(screen.getByText('飞书')).toBeVisible();
    expect(screen.getByText(/明镜 · .*2026.*10.*18.*09:15/)).toBeVisible();
  });
  it('keeps an authoritative empty core4 history answer and starts a new turn for its question', async () => {
    const nextTurn = vi.fn(),
      resume = vi.fn();
    render(
      <HistoryMessage
        row={{
          role: 'assistant',
          at: '',
          source: 'web',
          cursor: 'core4-question',
          turn_id: 'core4-question',
          content: '不应恢复的旧片段',
          meta: {
            schema: 'core4.0',
            text: '',
            asked: { question: '下一步先做什么？', options: ['先问清楚'], allow_free_text: true, why: '缩小问题' },
          },
        }}
        restore={() => undefined}
        resume={resume}
        onAskReply={nextTurn}
      />,
    );
    expect(screen.queryByText('不应恢复的旧片段')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '先问清楚' }));
    expect(nextTurn).toHaveBeenCalledWith('先问清楚');
    expect(resume).not.toHaveBeenCalled();
  });
  it('hides program profile commands and structured birth evidence outside the profile page', () => {
    const raw =
      '请更正这条已授权的记忆：请保存我已核对并确认的出生与性别资料：\ngender：女\nbirth.solar_datetime：1998-03-12 00:00\nbirth.location.lng：116.4';
    const { container } = render(
      <>
        <HistoryMessage
          row={{
            role: 'user',
            at: '2026-10-18T01:15:00Z',
            content: raw,
            source: 'web-action',
            cursor: 'synthetic-profile',
            turn_id: 'synthetic-profile',
          }}
          restore={() => undefined}
        />
        <HistoryMessage
          row={{
            role: 'assistant',
            at: '2026-10-18T01:15:01Z',
            content: '公开回答',
            source: 'web',
            cursor: 'synthetic-answer',
            turn_id: 'synthetic-profile',
            meta: {
              answer: '公开回答',
              evidence: [
                { ref: 'fact:synthetic', claim: 'birth.solar_datetime：1998-03-12 00:00' },
                { ref: 'fact:ordinary', claim: '面试在2026-10-21，想先准备简历' },
              ],
            },
          }}
          restore={() => undefined}
        />
      </>,
    );
    expect(container.textContent).not.toMatch(/1998-03-12|116\.4|birth\./);
    expect(screen.getByText('已核对出生资料，原值请到资料页查看')).toBeVisible();
    expect(screen.getByText('面试在2026-10-21，想先准备简历')).toBeInTheDocument();
  });
  it('does not query private history while login is required', async () => {
    useAuth.setState({ token: '', loginRequired: true });
    const fetcher = vi.fn();
    vi.stubGlobal('fetch', fetcher);
    const query = new QueryClient();
    render(
      <QueryClientProvider client={query}>
        <Chat />
      </QueryClientProvider>,
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('keeps two completed turns while history is refreshing and assigns a fresh second request ID', async () => {
    sessionStorage.clear();
    useAuth.setState({ token: 'synthetic-token', loginRequired: false });
    const ids: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string, init?: RequestInit) => {
        if (path.startsWith('/api/history')) return Response.json([]);
        const payload = JSON.parse(String(init?.body)) as { request_id: string; message: string };
        ids.push(payload.request_id);
        return new Response(
          `data: ${JSON.stringify({ type: 'started', run_id: 'synthetic-' + ids.length })}\n\ndata: ${JSON.stringify({ type: 'result', result: { answer: '回答：' + payload.message } })}\n\n`,
        );
      }),
    );
    const query = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={query}>
        <Chat />
      </QueryClientProvider>,
    );
    for (const message of ['第一轮', '第二轮']) {
      await userEvent.type(screen.getByRole('textbox', { name: '和明镜说说' }), message);
      await userEvent.click(screen.getByRole('button', { name: '发送' }));
      await screen.findByText(`回答：${message}`);
    }
    expect(screen.getByText('回答：第一轮')).toBeVisible();
    expect(screen.getByText('回答：第二轮')).toBeVisible();
    expect(ids).toHaveLength(2);
    expect(ids[0]).not.toBe(ids[1]);
    useAuth.setState({ token: '', loginRequired: true });
  });
  it('keeps an unconfirmed early cancellation pending and never claims the run stopped', async () => {
    sessionStorage.clear();
    useAuth.setState({ token: '', loginRequired: true });
    let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
    const requests: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string) => {
        requests.push(path);
        if (path.endsWith('/cancel')) return Response.json({ detail: 'missing req' }, { status: 422 });
        return new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              streamController = controller;
            },
          }),
        );
      }),
    );
    const query = new QueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={query}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useChat(), { wrapper });
    act(() => {
      void result.current.send('取消前未收到运行标识', []);
    });
    await waitFor(() => expect(result.current.pending).toBeDefined());
    const id = result.current.pending!.payload.request_id;
    await act(() => result.current.cancel());
    expect(requests).toContain(`/api/runs/${id}/cancel`);
    expect(loadPending()?.payload.request_id).toBe(id);
    expect(result.current.error).toBeTruthy();
    expect(result.current.state.status).not.toBe('已停止本轮');
    await act(async () => {
      streamController!.enqueue(
        new TextEncoder().encode('data: {"type":"result","result":{"answer":"已保存的回答"}}\n\n'),
      );
      streamController!.close();
    });
  });
});
