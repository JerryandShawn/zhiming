import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Button } from '../src/components/ui/Controls';
import { Panel } from '../src/components/ui/Overlays';
import { usePanelHistory } from '../src/usePanelHistory';

beforeEach(() => {
  history.replaceState({ page: 'previous' }, '', '/#/today');
  history.pushState({ page: 'chart' }, '', '/#/chart');
});
function Example() {
  return (
    <>
      <textarea aria-label="对话草稿" />
      <Panel title="依据说明" description="本地合成说明" trigger={<Button>查看依据</Button>}>
        <input aria-label="面板输入" />
        <a href="#/me">前往关于我</a>
      </Panel>
    </>
  );
}
const settled = () => waitFor(() => expect(history.state).toEqual({ page: 'chart' }));

describe('same-URL panel history', () => {
  it('closes the panel on the first Back and leaves the page only on the next Back', async () => {
    render(<Example />);
    await userEvent.type(screen.getByRole('textbox', { name: '对话草稿' }), '保留这段合成草稿');
    const trigger = screen.getByRole('button', { name: '查看依据' });
    await userEvent.click(trigger);
    expect(location.hash).toBe('#/chart');
    expect(history.state).toMatchObject({ page: 'chart', __mingjing_panel: expect.any(String) });
    act(() => history.back());
    await settled();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(screen.getByRole('textbox', { name: '对话草稿' })).toHaveValue('保留这段合成草稿');
    expect(location.hash).toBe('#/chart');
    act(() => history.back());
    await waitFor(() => expect(location.hash).toBe('#/today'));
  });

  it.each(['Escape', '关闭'])('consumes its own history entry when dismissed with %s', async (command) => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: '查看依据' }));
    if (command === 'Escape') await userEvent.keyboard('{Escape}');
    else await userEvent.click(screen.getByRole('button', { name: '关闭' }));
    await settled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    act(() => history.back());
    await waitFor(() => expect(location.hash).toBe('#/today'));
  });

  it('does not reopen a dismissed dialog when Forward reaches its old marker', async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: '查看依据' }));
    const marker = history.state.__mingjing_panel;
    await userEvent.keyboard('{Escape}');
    await settled();
    act(() => history.forward());
    await waitFor(() => expect(history.state.__mingjing_panel).toBe(marker));
    expect(location.hash).toBe('#/chart');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes on a route change without issuing an extra Back that would undo navigation', async () => {
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: '查看依据' }));
    const back = vi.spyOn(history, 'back');
    await userEvent.click(screen.getByRole('link', { name: '前往关于我' }));
    await waitFor(() => expect(location.hash).toBe('#/me'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(back).not.toHaveBeenCalled();
  });

  it('waits for a retiring marker before opening again, rather than consuming the new panel entry', async () => {
    const { result } = renderHook(usePanelHistory);
    act(() => result.current.onOpenChange(true));
    const previous = history.state.__mingjing_panel;
    act(() => {
      result.current.onOpenChange(false);
      result.current.onOpenChange(true);
    });
    expect(result.current.open).toBe(false);
    await waitFor(() => expect(result.current.open).toBe(true));
    expect(history.state.__mingjing_panel).not.toBe(previous);
    act(() => result.current.onOpenChange(false));
    await settled();
    expect(result.current.open).toBe(false);
  });

  it('keeps the dialog usable and never navigates Back if history push is unavailable', async () => {
    vi.spyOn(history, 'pushState').mockImplementation(() => {
      throw new DOMException('Unavailable', 'SecurityError');
    });
    const back = vi.spyOn(history, 'back');
    render(<Example />);
    await userEvent.click(screen.getByRole('button', { name: '查看依据' }));
    expect(screen.getByRole('dialog', { name: '依据说明' })).toBeVisible();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(back).not.toHaveBeenCalled();
  });
});
