import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ItemEditor } from '../src/night/me/ItemEditor';
import { ConfirmAction } from '../src/night/me/ConfirmAction';
import { createAboutMeStore } from '../src/night/me/port';
import { AboutMeError, type AboutMePort, type AboutMeReceipt } from '../src/night/me/types';

function setup(kind: 'profile' | 'memory', execute?: AboutMePort['execute']) {
  const base = createAboutMeStore();
  const command = vi.fn(execute ?? base.execute);
  const item = kind === 'profile' ? base.getSnapshot().profileItems[0] : base.getSnapshot().memories[0];
  const close = vi.fn(),
    confirmed = vi.fn();
  render(
    <ItemEditor item={item} kind={kind} port={{ ...base, execute: command }} close={close} confirmed={confirmed} />,
  );
  return { base, command, close, confirmed, field: screen.getByRole('textbox', { name: '你的说法' }) };
}

describe('definitive local About Me validation rejection', () => {
  for (const kind of ['profile', 'memory'] as const)
    for (const invalid of ['overlong', 'birth-field'] as const)
      it(`keeps ${kind} ${invalid} draft editable after zero-write local INVALID/422`, async () => {
        const state = setup(kind),
          before = state.base.getSnapshot();
        // fireEvent intentionally covers programmatic/history data even if a
        // future native maxLength prevents typing the complete overlong value.
        const rejected = invalid === 'overlong' ? '合'.repeat(2001) : '出生日期：2099-01-01（合成校验样本）';
        fireEvent.change(state.field, { target: { value: rejected } });
        fireEvent.submit(state.field.closest('form')!);
        await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('尚未保存'));
        expect(state.base.getSnapshot()).toBe(before);
        expect(state.close).not.toHaveBeenCalled();
        expect(state.confirmed).not.toHaveBeenCalled();
        expect(state.field).toHaveValue(rejected);
        expect(state.field).toBeEnabled();
        expect(screen.queryByRole('button', { name: '用原操作重试' })).not.toBeInTheDocument();
        const safe = `现在可继续修正的合成${kind === 'profile' ? '画像' : '记忆'}摘要`;
        fireEvent.change(state.field, { target: { value: safe } });
        await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
        await waitFor(() => expect(state.close).toHaveBeenCalledTimes(1));
        expect(state.confirmed).toHaveBeenCalledTimes(1);
        expect(state.command).toHaveBeenCalledTimes(2);
        expect(state.command.mock.calls[0][0]).toMatchObject({ text: rejected, expectedRevision: 1 });
        expect(state.command.mock.calls[1][0]).toMatchObject({ text: safe, expectedRevision: 1 });
        expect(state.command.mock.calls[1][0].requestId).not.toBe(state.command.mock.calls[0][0].requestId);
        expect(state.base.getSnapshot().revision).toBe(before.revision + 1);
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      });

  for (const [name, reason] of [
    ['network', new AboutMeError('NETWORK', 0, 'PRIVATE_BACKEND_BODY')],
    ['rate limit', new AboutMeError('RATE_LIMIT', 429, 'PRIVATE_BACKEND_BODY')],
    ['untyped numeric 422', { status: 422, message: 'PRIVATE_BACKEND_BODY' }],
    ['mismatched typed error', new AboutMeError('NETWORK', 422, 'PRIVATE_BACKEND_BODY')],
  ] as const)
    it(`does not release the original immutable request for ${name}`, async () => {
      const base = createAboutMeStore();
      const execute = vi
        .fn<AboutMePort['execute']>()
        .mockRejectedValueOnce(reason)
        .mockImplementation((command) => base.execute(command));
      const close = vi.fn();
      render(
        <ItemEditor
          item={base.getSnapshot().profileItems[0]}
          kind="profile"
          port={{ ...base, execute }}
          close={close}
          confirmed={vi.fn()}
        />,
      );
      const field = screen.getByRole('textbox', { name: '你的说法' });
      fireEvent.change(field, { target: { value: '明确保留的合成请求' } });
      await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
      await waitFor(() => expect(screen.getByRole('button', { name: '用原操作重试' })).toBeEnabled());
      expect(field).toBeDisabled();
      expect(screen.getByRole('alert')).not.toHaveTextContent('PRIVATE_BACKEND_BODY');
      expect(base.getSnapshot().revision).toBe(1);
      await userEvent.click(screen.getByRole('button', { name: '用原操作重试' }));
      await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
      expect(execute.mock.calls[1][0]).toBe(execute.mock.calls[0][0]);
      expect(base.getSnapshot().revision).toBe(2);
    });

  it('keeps the same request after a malformed receipt instead of assuming a zero-write rejection', async () => {
    const base = createAboutMeStore();
    const execute = vi.fn<AboutMePort['execute']>();
    execute.mockImplementationOnce(async (command): Promise<AboutMeReceipt> => ({
      id: command.id,
      kind: command.type,
      requestId: 'wrong-request',
      revision: 2,
      snapshotRevision: 2,
      write_status: 'saved',
      affectedIds: [command.id],
    }));
    execute.mockImplementation((command) => base.execute(command));
    const close = vi.fn();
    render(
      <ItemEditor
        item={base.getSnapshot().profileItems[0]}
        kind="profile"
        port={{ ...base, execute }}
        close={close}
        confirmed={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByRole('textbox', { name: '你的说法' }), { target: { value: '合成核对草稿' } });
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    expect(screen.getByRole('textbox', { name: '你的说法' })).toBeDisabled();
    expect(close).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '用原操作重试' }));
    await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
    expect(execute.mock.calls[1][0]).toBe(execute.mock.calls[0][0]);
  });

  it('does not broaden editable-draft recovery to a pending deletion confirmation', async () => {
    const base = createAboutMeStore();
    const execute = vi
      .fn<AboutMePort['execute']>()
      .mockRejectedValueOnce(new AboutMeError('INVALID', 422, 'PRIVATE_BACKEND_BODY'))
      .mockImplementation((command) => base.execute(command));
    const close = vi.fn();
    render(
      <ConfirmAction
        port={{ ...base, execute }}
        command={{ type: 'profile-delete', id: 'profile-basic', expectedRevision: 1, requestId: 'local-delete' }}
        text="合成确认操作"
        label="确认删除画像条目"
        close={close}
        confirmed={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: '确认删除画像条目' }));
    expect(base.getSnapshot().revision).toBe(1);
    await userEvent.click(screen.getByRole('button', { name: '用原操作重试' }));
    await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
    expect(execute.mock.calls[1][0]).toBe(execute.mock.calls[0][0]);
  });
});
