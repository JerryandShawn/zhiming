import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DraftOrganizePage from '../src/organize/DraftOrganizePage';

describe('draft organize review page', () => {
  it('reviews the exact plan but shows the record_only quality gate instead of claiming application', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch');
    render(<DraftOrganizePage preview />);
    expect(await screen.findByRole('heading', { name: '合成话题' })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '审阅当前计划' }));
    expect(await screen.findByText(/审阅凭证已签发/)).toBeVisible();
    expect(screen.getByText(/审阅凭证不代表质量门已开放/)).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '核对应用资格' }));
    expect(await screen.findByText('这项整理尚未开放自动应用。')).toBeVisible();
    expect(screen.queryByText('应用已由程序回执确认。')).not.toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('saves a rename, invalidates the old review and requires a fresh plan review', async () => {
    render(<DraftOrganizePage preview />);
    const input = await screen.findByRole('textbox', { name: '话题名称' });
    await userEvent.clear(input);
    await userEvent.type(input, '新话题名');
    await userEvent.click(screen.getByRole('button', { name: '保存改名' }));
    expect(await screen.findByText('改名已保存，旧审阅已失效，请重新核对计划。')).toBeVisible();
    expect(screen.getByRole('heading', { name: '新话题名' })).toBeVisible();
    expect(screen.getByRole('button', { name: '核对应用资格' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '审阅当前计划' }));
    expect(await screen.findByText(/审阅凭证已签发/)).toBeVisible();
    expect(screen.getByRole('button', { name: '核对应用资格' })).toBeEnabled();
  });
});
