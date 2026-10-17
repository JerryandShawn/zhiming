import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Button, Switch } from '../src/components/ui/Controls';
import { Panel } from '../src/components/ui/Overlays';
import { Markdown } from '../src/components/Markdown';
import { AskCard, Composer, DecisionCard, MemoryReceipt, ToolStatusLine } from '../src/components/Messages';
import { CardPicker, RevealSpread, SpreadLayout } from '../src/components/TarotCards';
import Tarot from '../src/pages/Tarot';
import { useUi } from '../src/state';
import backAsset from '../../static/tarot/back.svg';

describe('M1 component contracts', () => {
  it('keeps the loading label and prevents duplicate activation', async () => {
    const click = vi.fn();
    render(
      <Button loading onClick={click}>
        继续
      </Button>,
    );
    const button = screen.getByRole('button', { name: '继续' });
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(click).not.toHaveBeenCalled();
  });
  it('uses a named, keyboard operable switch', async () => {
    const change = vi.fn();
    render(<Switch label="晨报" checked={false} onChange={change} />);
    const control = screen.getByRole('switch', { name: '晨报' });
    control.focus();
    await userEvent.keyboard(' ');
    expect(change).toHaveBeenCalledWith(true);
  });
  it('returns focus to the trigger when Escape closes a dialog', async () => {
    render(
      <Panel title="修改条目" description="内容不会发送。" trigger={<Button>打开</Button>}>
        <input aria-label="你的说法" />
      </Panel>,
    );
    const trigger = screen.getByRole('button', { name: '打开' });
    await userEvent.click(trigger);
    expect(screen.getByRole('dialog', { name: '修改条目' })).toBeVisible();
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(trigger).toHaveFocus());
  });
  it('sanitizes executable and remote HTML without raw HTML insertion', () => {
    const { container } = render(
      <Markdown
        text={
          '**保留粗体**<script>alert(1)</script><img src="https://bad.example/x"><iframe></iframe><form><input></form><style>body{display:none}</style>[坏链接](javascript:alert(1))'
        }
      />,
    );
    expect(screen.getByText('保留粗体').tagName).toBe('STRONG');
    expect(container.querySelectorAll('script,img,iframe,form,style,input')).toHaveLength(0);
    expect(container.querySelector('a')?.getAttribute('href')).not.toMatch(/^javascript:/);
  });
  it('asks one concrete question and records only the local selection', async () => {
    render(<AskCard />);
    await userEvent.click(screen.getByRole('button', { name: '技术面' }));
    expect(screen.getByRole('button', { name: '技术面' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('你选了：技术面')).toBeVisible();
    expect(screen.getByRole('button', { name: '还不确定' })).toBeDisabled();
  });
  it('moves free-text focus to the composer', async () => {
    render(
      <>
        <AskCard />
        <Composer />
      </>,
    );
    await userEvent.click(screen.getByRole('button', { name: '我自己说' }));
    expect(screen.getByRole('textbox', { name: '和明镜说说' })).toHaveFocus();
  });
  it('shows all five decision dimensions for both options', () => {
    render(<DecisionCard />);
    for (const name of ['收益', '代价', '风险', '可逆性', '第一步']) expect(screen.getAllByText(name)).toHaveLength(2);
  });
  it.each(['saved', 'pending', 'undone'] as const)('renders the %s receipt state', (state) => {
    render(<MemoryReceipt state={state} />);
    expect(
      screen.getByText(state === 'saved' ? /记下了/ : state === 'pending' ? /这个比较私人/ : /已撤销/),
    ).toBeVisible();
  });
  it('keeps completed tool steps folded until explicitly expanded', async () => {
    render(<ToolStatusLine />);
    const details = screen.getByText('查看步骤').closest('details');
    expect(details).not.toHaveAttribute('open');
    fireEvent.click(screen.getByText('查看步骤'));
    expect(details).toHaveAttribute('open');
  });
  it('keeps unrevealed card faces absent from the DOM', () => {
    render(<SpreadLayout faceUp={false} />);
    expect(screen.getAllByRole('img')).toHaveLength(3);
    for (const image of screen.getAllByRole('img')) expect(image.getAttribute('src')).toBe(backAsset);
    expect(screen.queryByText('星星')).not.toBeInTheDocument();
  });
  it('moves card focus with arrows and prevents duplicate selections', async () => {
    render(<CardPicker />);
    const first = screen.getByRole('button', { name: '第1张牌' });
    first.focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('button', { name: '第2张牌' })).toHaveFocus();
    await userEvent.click(first);
    await userEvent.click(first);
    expect(screen.getByRole('status')).toHaveTextContent('已选 1 / 3');
  });
  it('keeps the static composer from making a network request', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch');
    render(<Composer />);
    await userEvent.type(screen.getByRole('textbox'), '一段合成内容');
    await userEvent.click(screen.getByRole('button', { name: '发送' }));
    expect(fetch).not.toHaveBeenCalled();
    expect(useUi.getState().toast).toContain('不会发送');
  });
  it('falls back to system theme if storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('unavailable');
    });
    useUi.getState().setTheme('dark');
    expect(useUi.getState().theme).toBe('system');
    expect(document.documentElement.dataset.theme).toBe('light');
  });
  it('reveals a fixed sample card only after explicit selection', async () => {
    render(<RevealSpread />);
    expect(screen.queryByRole('img', { name: '星星正位' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '揭开第3张牌' }));
    expect(screen.getByRole('img', { name: '星星正位' })).toBeInTheDocument();
    expect(screen.getAllByRole('img', { name: '不透明的塔罗牌背' })).toHaveLength(2);
  });
  it('requires two nonempty distinct A/B options before starting', async () => {
    render(<Tarot />);
    await userEvent.click(screen.getByRole('button', { name: /新问题/ }));
    await userEvent.click(screen.getByRole('button', { name: /A\/B选择/ }));
    const start = screen.getByRole('button', { name: '开始（合成示例）' });
    await userEvent.type(screen.getByRole('textbox', { name: '选项A' }), '留在现在');
    expect(start).toBeDisabled();
    await userEvent.type(screen.getByRole('textbox', { name: '选项B' }), '跳槽');
    expect(start).toBeEnabled();
  });
});
