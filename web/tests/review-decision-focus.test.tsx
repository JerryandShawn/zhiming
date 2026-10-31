import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createHash } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';
import OrganizeReviewPage from '../src/organize/OrganizeReviewPage';
import { createOrganizeDemoPort } from '../src/organize/port';
import type { OrganizePort } from '../src/organize/types';

// Uses the real local draft adapter; remote model and storage APIs are absent.
const digest = async (value: string) => createHash('sha256').update(value).digest('hex');
const createPort = () => createOrganizeDemoPort({ now: () => Date.parse('2026-10-21T07:15:00+08:00'), digest });
function gate() {
  let resolve!: () => void;
  const promise = new Promise<void>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}
function article(id = 'segment-1') {
  const element = Array.from(document.querySelectorAll<HTMLElement>('[data-segment-id]')).find(
    (node) => node.dataset.segmentId === id,
  );
  if (!element) throw new Error('Synthetic review segment missing');
  return element;
}
function delayed() {
  const base = createPort(),
    ready = gate();
  const edit = vi.fn<OrganizePort['edit']>((command) => ready.promise.then(() => base.edit(command)));
  return { base, ready, edit, port: { ...base, edit } };
}
async function decide(kind: 'accept' | 'reject', id = 'segment-1') {
  const button = within(article(id)).getByRole('button', { name: kind === 'accept' ? '接受' : '拒绝' });
  button.focus();
  await userEvent.keyboard('{Enter}');
  return button;
}
async function accepted(port: OrganizePort, kind: 'accept' | 'reject' = 'accept', id = 'segment-1') {
  await waitFor(() =>
    expect(port.getSnapshot().segments.find((item) => item.id === id)?.decision).toBe(
      kind === 'accept' ? 'accepted' : 'rejected',
    ),
  );
}

describe('focus after an explicit review decision', () => {
  it.each(['accept', 'reject'] as const)(
    'focuses the remounted fragment after an uncertain %s decision',
    async (kind) => {
      const port = createPort(),
        original = structuredClone(port.getSnapshot().document);
      render(<OrganizeReviewPage suppliedPort={port} />);
      const before = article();
      await decide(kind);
      await accepted(port, kind);
      const after = article();
      expect(after).not.toBe(before);
      await waitFor(() => expect(after).toHaveFocus());
      expect(after).toHaveAttribute('tabindex', '-1');
      expect(screen.getByRole('region', { name: '不确定，待你整理' })).not.toContainElement(after);
      expect(port.getSnapshot().document).toEqual(original);
    },
  );

  it('repairs focus when the same article stays mounted but its chosen action becomes disabled', async () => {
    const port = createPort();
    render(<OrganizeReviewPage suppliedPort={port} />);
    const before = article('segment-2');
    const button = await decide('accept', 'segment-2');
    await accepted(port, 'accept', 'segment-2');
    expect(article('segment-2')).toBe(before);
    expect(button).toBeDisabled();
    await waitFor(() => expect(before).toHaveFocus());
  });

  it('preserves a focus choice made outside the fragment while the command is pending', async () => {
    const { base, ready, port, edit } = delayed();
    render(
      <>
        <button>查看其他内容</button>
        <OrganizeReviewPage suppliedPort={port} />
      </>,
    );
    await decide('accept');
    expect(edit).toHaveBeenCalledTimes(1);
    const elsewhere = screen.getByRole('button', { name: '查看其他内容' });
    await userEvent.click(elsewhere);
    expect(elsewhere).toHaveFocus();
    await act(async () => {
      ready.resolve();
      await ready.promise;
    });
    await accepted(base);
    expect(elsewhere).toHaveFocus();
    expect(edit.mock.calls[0][0].intent).toEqual({ kind: 'accept', segment_id: 'segment-1' });
  });

  it('does not revive a canceled restoration after the user has moved elsewhere and then blurred', async () => {
    const { base, ready, port } = delayed();
    render(
      <>
        <button>先去别处</button>
        <OrganizeReviewPage suppliedPort={port} />
      </>,
    );
    await decide('accept');
    const elsewhere = screen.getByRole('button', { name: '先去别处' });
    await userEvent.click(elsewhere);
    elsewhere.blur();
    expect(document.body).toHaveFocus();
    await act(async () => {
      ready.resolve();
      await ready.promise;
    });
    await accepted(base);
    expect(document.body).toHaveFocus();
  });

  it('uses the page heading when the relocated article is under a collapsed destination', async () => {
    const port = createPort();
    render(<OrganizeReviewPage suppliedPort={port} />);
    const snapshot = port.getSnapshot();
    const topic = snapshot.topics.find(
      (item) => item.id === snapshot.segments.find((item) => item.id === 'segment-1')!.topic_id,
    )!;
    const space = Array.from(document.querySelectorAll<HTMLDetailsElement>('[data-space-id]')).find(
      (node) => node.dataset.spaceId === topic.space_id,
    )!;
    space.open = false;
    await decide('accept');
    await accepted(port);
    expect(article().closest('details:not([open])')).toBe(space);
    await waitFor(() => expect(screen.getByRole('heading', { name: '旧对话审阅' })).toHaveFocus());
  });

  it('restores an enabled original action after a failed receipt instead of moving to another fragment', async () => {
    const base = createPort(),
      ready = gate();
    const edit = vi.fn<OrganizePort['edit']>(async (command) => {
      await ready.promise;
      return {
        status: 'rejected',
        request_id: command.request_id,
        revision: base.getSnapshot().revision,
        message: '合成未写入，仍可重试。',
      };
    });
    render(<OrganizeReviewPage suppliedPort={{ ...base, edit }} />);
    const button = await decide('accept');
    // jsdom retains focus on disabled buttons; reproduce the browser's body fallback.
    document.body.tabIndex = -1;
    document.body.focus();
    document.body.removeAttribute('tabindex');
    expect(document.body).toHaveFocus();
    await act(async () => {
      ready.resolve();
      await ready.promise;
    });
    expect(await screen.findByText('合成未写入，仍可重试。')).toBeVisible();
    await waitFor(() => expect(button).toHaveFocus());
    expect(button).not.toBeDisabled();
    expect(base.getSnapshot().revision).toBe(1);
  });

  it('does not move focus for a snapshot change that was not started from a focused decision action', async () => {
    const port = createPort();
    render(<OrganizeReviewPage suppliedPort={port} />);
    expect(document.body).toHaveFocus();
    await act(() =>
      port.edit({
        request_id: 'external-synthetic-accept',
        expected_revision: 1,
        intent: { kind: 'accept', segment_id: 'segment-1' },
      }),
    );
    await accepted(port);
    expect(document.body).toHaveFocus();
  });
});
