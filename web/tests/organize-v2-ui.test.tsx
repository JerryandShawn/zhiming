import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createHash } from 'node:crypto';
import { expect, it, vi } from 'vitest';
import OrganizeReviewPage from '../src/organize/OrganizeReviewPage';
import { createOrganizeDemoPort, ORGANIZE_CONFIRMATION_TTL_MS } from '../src/organize/port';
import type { OrganizePort } from '../src/organize/types';

const initialTime = Date.parse('2026-10-21T00:00:00+08:00');
const digest = async (text: string) => createHash('sha256').update(text).digest('hex');
function setup() {
  let now = initialTime;
  const port = createOrganizeDemoPort({ now: () => now, digest });
  return {
    port,
    advance: (milliseconds: number) => {
      now += milliseconds;
    },
  };
}
async function accept(port: OrganizePort, id = 'segment-2') {
  await port.edit({
    request_id: `accept-${id}`,
    expected_revision: port.getSnapshot().revision,
    intent: { kind: 'accept', segment_id: id },
  });
}
async function applyPage() {
  await userEvent.click(screen.getByRole('button', { name: '应用已接受的整理' }));
  await userEvent.click(screen.getByRole('button', { name: '确认应用' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
}

it('requires an accepted segment and a second confirmation; cancel changes no source labels', async () => {
  const { port } = setup(),
    execute = vi.fn(port.execute);
  render(<OrganizeReviewPage suppliedPort={{ ...port, execute }} />);
  expect(screen.getByRole('button', { name: '应用已接受的整理' })).toBeDisabled();
  const original = structuredClone(port.getSnapshot().document);
  await act(() => accept(port));
  await userEvent.click(screen.getByRole('button', { name: '应用已接受的整理' }));
  expect(screen.getByRole('dialog')).toHaveTextContent('15分钟内有效');
  await userEvent.click(screen.getByRole('button', { name: '取消' }));
  expect(execute).not.toHaveBeenCalled();
  expect(port.getSnapshot().document).toEqual(original);
  expect(screen.getByRole('button', { name: '应用已接受的整理' })).toHaveFocus();
  await applyPage();
  expect(port.getSnapshot().document.messages['message-2'].topic_id).toBe('proposal-2');
  expect(port.getSnapshot().document.messages['message-1']).toEqual(original.messages['message-1']);
});

it('expires an apply confirmation exactly at 15 minutes and renews without writing', async () => {
  const { port, advance } = setup();
  await accept(port);
  render(<OrganizeReviewPage suppliedPort={port} />);
  await userEvent.click(screen.getByRole('button', { name: '应用已接受的整理' }));
  advance(ORGANIZE_CONFIRMATION_TTL_MS);
  await userEvent.click(screen.getByRole('button', { name: '确认应用' }));
  expect(screen.getByRole('alert')).toHaveTextContent('这张卡已过期，我重新发一张');
  expect(port.getSnapshot().status).toBe('draft');
  await userEvent.click(screen.getByRole('button', { name: '重新确认' }));
  expect(port.getSnapshot().status).toBe('draft');
  await userEvent.click(screen.getByRole('button', { name: '确认应用' }));
  await waitFor(() => expect(port.getSnapshot().status).toBe('applied'));
});

it.each(['whole', 'fields'])('requires an unexpired second confirmation for %s undo', async (kind) => {
  const { port, advance } = setup();
  await accept(port);
  render(<OrganizeReviewPage suppliedPort={port} />);
  await applyPage();
  if (kind === 'fields') await userEvent.click(screen.getAllByRole('checkbox')[0]);
  await userEvent.click(screen.getByRole('button', { name: kind === 'whole' ? '撤销整批整理' : '撤销所选字段' }));
  const original = structuredClone(port.getSnapshot().document);
  advance(ORGANIZE_CONFIRMATION_TTL_MS);
  await userEvent.click(screen.getByRole('button', { name: '确认撤销' }));
  expect(screen.getByRole('alert')).toHaveTextContent('这张卡已过期，我重新发一张');
  expect(port.getSnapshot().document).toEqual(original);
  await userEvent.click(screen.getByRole('button', { name: '取消' }));
  expect(port.getSnapshot().document).toEqual(original);
});

it('restores selected routing fields while leaving another accepted fragment applied', async () => {
  const { port } = setup();
  await accept(port);
  await accept(port, 'segment-3');
  render(<OrganizeReviewPage suppliedPort={port} />);
  await applyPage();
  const firstRoute = document.querySelector<HTMLElement>(
    '[data-field-key=\'["messages","message-2","route_confidence"]\']',
  );
  expect(firstRoute).toBeTruthy();
  await userEvent.click(within(firstRoute!).getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: '撤销所选字段' }));
  await userEvent.click(screen.getByRole('button', { name: '确认撤销' }));
  await waitFor(() => expect(port.getSnapshot().status).toBe('partially_reverted'));
  expect(port.getSnapshot().document.messages['message-2'].topic_id).toBe('legacy-all');
  expect(port.getSnapshot().document.messages['message-3'].topic_id).toBe('proposal-3');
  await userEvent.click(screen.getByRole('button', { name: '撤销整批整理' }));
  await userEvent.click(screen.getByRole('button', { name: '确认撤销' }));
  await waitFor(() => expect(port.getSnapshot().status).toBe('reverted'));
  expect(port.getSnapshot().document.messages['message-3'].topic_id).toBe('legacy-all');
});

it('does not close on a mismatched apply receipt and retries the same command identity', async () => {
  const { port } = setup();
  await accept(port);
  const execute = vi
    .fn<OrganizePort['execute']>()
    .mockImplementationOnce(async (command) => ({
      status: 'accepted',
      request_id: `${command.request_id}-wrong`,
      revision: port.getSnapshot().revision,
      message: 'invalid',
    }))
    .mockImplementation(port.execute);
  render(<OrganizeReviewPage suppliedPort={{ ...port, execute }} />);
  await userEvent.click(screen.getByRole('button', { name: '应用已接受的整理' }));
  await userEvent.click(screen.getByRole('button', { name: '确认应用' }));
  expect(screen.getByRole('dialog')).toBeVisible();
  expect(screen.getByRole('alert')).toHaveTextContent('回执尚未核对成功');
  expect(port.getSnapshot().status).toBe('draft');
  await userEvent.click(screen.getByRole('button', { name: '确认应用' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(execute.mock.calls[0][0]).toEqual(execute.mock.calls[1][0]);
});

it('allows excluding a withdrawn candidate so another valid accepted segment can still apply', async () => {
  const { port } = setup();
  await accept(port);
  await accept(port, 'segment-3');
  render(<OrganizeReviewPage suppliedPort={port} />);
  const next = structuredClone(port.getSnapshot().document);
  next.messages['message-2'].status = 'withdrawn';
  act(() => port.refresh(next));
  const source = document.querySelector<HTMLElement>('[data-segment-id="segment-2"]')!;
  expect(source).not.toHaveTextContent('想练习怎样把项目经过说清楚。');
  expect(within(source).getByRole('button', { name: '接受' })).toBeDisabled();
  expect(within(source).getByRole('button', { name: '移动' })).toBeDisabled();
  await userEvent.click(within(source).getByRole('button', { name: '拒绝' }));
  await waitFor(() => expect(port.getSnapshot().summary.accepted_segments).toBe(1));
  await applyPage();
  expect(port.getSnapshot().document.messages['message-2'].topic_id).toBe('legacy-all');
  expect(port.getSnapshot().document.messages['message-2'].status).toBe('withdrawn');
  expect(port.getSnapshot().document.messages['message-3'].topic_id).toBe('proposal-3');
});
