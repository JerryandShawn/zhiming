import { useLayoutEffect } from 'react';
import { act, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { createToolDemoPort } from '../src/tools/port';
import { useToolRead } from '../src/tools/useToolRead';
import SynastryPage from '../src/tools/SynastryPage';
import type { ToolPort } from '../src/tools/types';
import { gate, synastryFixture } from './tools-test-fixtures';

vi.mock('../src/tools/SynastryResults', () => ({
  default: ({ sample }: { sample: { document_id: string } }) => (
    <div data-tool-document={sample.document_id}>只读合成结果</div>
  ),
}));

describe('tool read render ownership', () => {
  it('hides the previous ready view before passive effects run', async () => {
    const first = createToolDemoPort([]),
      second = first.createScope(),
      seen: string[] = [];
    let read!: ReturnType<typeof useToolRead<number>>;
    function Probe({ port }: { port: ToolPort }) {
      read = useToolRead<number>(port);
      useLayoutEffect(() => {
        seen.push(`${port === first ? 'first' : 'second'}:${read.view.status}`);
      });
      return <span>{read.view.status}</span>;
    }
    const mounted = render(<Probe port={first} />);
    await act(async () => {
      await read.run(async () => ({ status: 'ready', sample: 1 }));
    });
    expect(screen.getByText('ready')).toBeVisible();
    mounted.rerender(<Probe port={second} />);
    expect(seen.at(-1)).toBe('second:idle');
  });

  it('does not resurrect a prior generation when returning to the same port', async () => {
    const first = createToolDemoPort([]),
      second = first.createScope();
    const hook = renderHook(({ port }) => useToolRead<number>(port), { initialProps: { port: first } });
    await act(async () => {
      await hook.result.current.run(async () => ({ status: 'ready', sample: 1 }));
    });
    hook.rerender({ port: second });
    hook.rerender({ port: first });
    expect(hook.result.current.view.status).toBe('idle');
  });

  it('ignores late success and late failure from a replaced owner', async () => {
    const first = createToolDemoPort([]),
      second = first.createScope(),
      late = gate<{ status: 'ready'; sample: number }>();
    const hook = renderHook(({ port }) => useToolRead<number>(port), { initialProps: { port: first } });
    let pending!: Promise<void>;
    act(() => {
      pending = hook.result.current.run(() => late.promise);
    });
    hook.rerender({ port: second });
    await act(async () => {
      await hook.result.current.run(async () => ({ status: 'ready', sample: 2 }));
    });
    await act(async () => {
      late.resolve({ status: 'ready', sample: 1 });
      await pending;
    });
    expect(hook.result.current.view).toEqual({ status: 'ready', sample: 2 });
    const failed = gate<{ status: 'ready'; sample: number }>();
    act(() => {
      pending = hook.result.current.run(() => failed.promise);
    });
    hook.rerender({ port: first });
    await act(async () => {
      failed.reject(new Error('private backend detail'));
      await pending;
    });
    expect(hook.result.current.view).toEqual({ status: 'idle' });
  });

  it('reset prevents late completion from replacing the empty view', async () => {
    const port = createToolDemoPort([]),
      late = gate<{ status: 'ready'; sample: number }>();
    const hook = renderHook(() => useToolRead<number>(port));
    let pending!: Promise<void>;
    act(() => {
      pending = hook.result.current.run(() => late.promise);
    });
    act(() => {
      hook.result.current.reset();
    });
    await act(async () => {
      late.resolve({ status: 'ready', sample: 1 });
      await pending;
    });
    expect(hook.result.current.view).toEqual({ status: 'idle' });
  });
});

const approve = () => {
  fireEvent.click(screen.getByRole('checkbox', { name: '允许本次展示A方合成盘面' }));
  fireEvent.click(screen.getByRole('checkbox', { name: '允许本次展示B方合成盘面' }));
};

describe('fresh display consent belongs to one viewer generation', () => {
  it('hides the ready chart and disables its confirmation on the first new-owner commit', async () => {
    const sample = synastryFixture(),
      first = createToolDemoPort([sample]),
      second = first.createScope();
    const frames: { document: boolean; allowed: boolean }[] = [];
    function Host({ port }: { port: ToolPort }) {
      useLayoutEffect(() => {
        const submit = document.querySelector<HTMLButtonElement>('button[type="submit"]');
        frames.push({
          document: Boolean(document.querySelector('[data-tool-document]')),
          allowed: Boolean(submit && !submit.disabled),
        });
      });
      return <SynastryPage port={port} />;
    }
    const mounted = render(<Host port={first} />);
    approve();
    fireEvent.click(screen.getByRole('button', { name: '查看已确认的样例' }));
    await screen.findByText('只读合成结果');
    mounted.rerender(<Host port={second} />);
    expect(frames.at(-1)).toEqual({ document: false, allowed: false });
    expect(screen.getByRole('checkbox', { name: '允许本次展示A方合成盘面' })).not.toBeChecked();
    expect(second.resolveEvidence(sample.evidence[0].ref)).toBeUndefined();
  });

  it('changing any condition withdraws both confirmations and active evidence', async () => {
    const sample = synastryFixture(),
      port = createToolDemoPort([sample]);
    render(<SynastryPage port={port} />);
    approve();
    fireEvent.click(screen.getByRole('button', { name: '查看已确认的样例' }));
    await screen.findByText('只读合成结果');
    expect(port.resolveEvidence(sample.evidence[0].ref)).toBeDefined();
    fireEvent.change(screen.getByLabelText('核对日期（北京时间）'), { target: { value: '2026-10-22' } });
    expect(screen.queryByText('只读合成结果')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看已确认的样例' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: '允许本次展示A方合成盘面' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: '允许本次展示B方合成盘面' })).not.toBeChecked();
    expect(port.resolveEvidence(sample.evidence[0].ref)).toBeUndefined();
  });

  it('withdrawing while loading never reveals a late result or evidence', async () => {
    const sample = synastryFixture(),
      waiting = gate<void>();
    const port = createToolDemoPort([sample], () => waiting.promise);
    render(<SynastryPage port={port} />);
    approve();
    fireEvent.click(screen.getByRole('button', { name: '查看已确认的样例' }));
    fireEvent.click(screen.getByRole('button', { name: '撤回本次展示' }));
    await act(async () => {
      waiting.resolve();
      await waiting.promise;
    });
    expect(screen.queryByText('只读合成结果')).not.toBeInTheDocument();
    expect(port.resolveEvidence(sample.evidence[0].ref)).toBeUndefined();
  });
});
