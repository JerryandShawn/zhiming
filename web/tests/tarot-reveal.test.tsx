import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Tarot from '../src/pages/Tarot';
import { RevealSpread } from '../src/components/TarotCards';
import { FlipFace } from '../src/tarot/FlipFace';
import { ServerSpread } from '../src/tarot/ServerSpread';
import { draw } from '../src/tarot/public';

const positions = ['过去的影响', '现在的状态', '可以怎么做'];
const hidden = {
  id: 'saved-fixed-draw',
  spread_id: 'reflect3',
  spread: { id: 'reflect3', positions },
  draw_source: 'auto',
  status: 'pending_reveal',
  cards: positions.map((label, index) => ({ position: index + 1, label, revealed: false, back_id: `opaque-${index}` })),
};
const visible = {
  ...hidden,
  status: 'ready',
  cards: hidden.cards.map((position, index) => ({
    ...position,
    revealed: true,
    orientation: index === 1 ? 'reversed' : 'upright',
    card: {
      card_id: `major-${index + 1}`,
      name: `合成牌${index + 1}`,
      upright: '先核对现实安排',
      reversed: '留意节奏',
      misreading: '不是结果保证',
      question: '下一步能做什么？',
    },
  })),
};

beforeEach(() => {
  window.history.replaceState(null, '', '#/tarot');
  vi.mocked(window.matchMedia).mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

describe('receipt-gated tarot reveals', () => {
  it('does not mount a hidden face or its SVG URL, even if a caller supplies an identity', () => {
    const view = render(<FlipFace revealed={false} frontImage="/private-face.svg" alt="PRIVATE_CARD" />);
    expect(document.body.innerHTML).not.toMatch(/private-face|PRIVATE_CARD|tarot-flip-front/);
    expect(screen.getByRole('img', { name: '不透明的塔罗牌背' })).toHaveAttribute('src', '/static/tarot/back.svg');
    view.rerender(<FlipFace revealed frontImage="/public-face.svg" alt="已揭开的合成牌" />);
    expect(screen.getByRole('img', { name: '已揭开的合成牌' })).toHaveAttribute('src', '/public-face.svg');
    expect(screen.queryByRole('img', { name: '不透明的塔罗牌背' })).not.toBeInTheDocument();
  });

  it('keeps all backs after a reveal request until the server confirms each public face', async () => {
    const mutate = vi.fn();
    const view = render(<ServerSpread draw={draw(hidden)} busy={false} mutate={mutate} />);
    await userEvent.click(screen.getByRole('button', { name: '揭开第2张牌' }));
    expect(mutate).toHaveBeenCalledExactlyOnceWith('reveal', { position: 2 });
    expect(screen.getAllByRole('img', { name: '不透明的塔罗牌背' })).toHaveLength(3);
    expect(document.querySelector('.tarot-flip-front')).toBeNull();
    view.rerender(
      <ServerSpread
        draw={draw({ ...hidden, cards: [hidden.cards[0], visible.cards[1], hidden.cards[2]] })}
        busy={false}
        mutate={mutate}
      />,
    );
    expect(screen.getByRole('img', { name: '合成牌2 · 逆位' })).toBeVisible();
    expect(screen.getAllByRole('img', { name: '不透明的塔罗牌背' })).toHaveLength(2);
    expect(document.querySelectorAll('.tarot-flip')[1]).toHaveStyle('--tarot-reveal-delay: 0ms');
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it('uses one all-reveal request and staggers the confirmed unchanged cards by 90ms', async () => {
    const mutate = vi.fn();
    const view = render(<ServerSpread draw={draw(hidden)} busy={false} mutate={mutate} />);
    await userEvent.click(screen.getByRole('button', { name: '全部揭开' }));
    expect(mutate).toHaveBeenCalledExactlyOnceWith('reveal', {});
    expect(document.querySelector('.tarot-flip-front')).toBeNull();
    view.rerender(<ServerSpread draw={draw(visible)} busy={false} mutate={mutate} />);
    expect(screen.getAllByRole('img', { name: /合成牌[0-9] ·/ })).toHaveLength(3);
    const faces = document.querySelectorAll('.tarot-flip');
    expect(faces[0]).toHaveStyle('--tarot-reveal-delay: 0ms');
    expect(faces[1]).toHaveStyle('--tarot-reveal-delay: 90ms');
    expect(faces[2]).toHaveStyle('--tarot-reveal-delay: 180ms');
    expect(screen.getByRole('region', { name: '每张牌的牌意与反思问题' })).toHaveTextContent('留意节奏');
    expect(document.querySelectorAll('.tarot-card details')).toHaveLength(0);
    expect(screen.getByText('逆位', { exact: true })).toBeVisible();
  });

  it('reveals immediately with zero stagger when reduced motion is requested', async () => {
    vi.mocked(window.matchMedia).mockImplementation((query) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    const mutate = vi.fn();
    const view = render(<ServerSpread draw={draw(hidden)} busy={false} mutate={mutate} />);
    await userEvent.click(screen.getByRole('button', { name: '全部揭开 · 跳过动画' }));
    view.rerender(<ServerSpread draw={draw(visible)} busy={false} mutate={mutate} />);
    document.querySelectorAll('.tarot-flip').forEach((face) => {
      expect(face).toHaveClass('no-motion');
      expect(face).toHaveAttribute('data-reduced-motion', 'true');
      expect(face).toHaveStyle('--tarot-reveal-delay: 0ms');
    });
    expect(mutate).toHaveBeenCalledExactlyOnceWith('reveal', {});
  });

  it('does not request another reveal for a locked or cancelled saved card', async () => {
    const mutate = vi.fn();
    render(<ServerSpread draw={draw({ ...hidden, status: 'cancelled' })} busy={false} mutate={mutate} />);
    await userEvent.click(screen.getByRole('button', { name: '揭开第1张牌' }));
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /^全部揭开/ })).not.toBeInTheDocument();
  });

  it('uses spread positions beneath the fixed five-card cross without inventing labels', () => {
    const labels = ['实际现状', '方案甲', '方案乙', '甲的发展', '乙的发展'];
    render(
      <ServerSpread
        draw={draw({
          ...hidden,
          spread_id: 'choice5',
          cards: labels.map((label, index) => ({ position: index + 1, label, revealed: false })),
        })}
        busy={false}
        mutate={vi.fn()}
      />,
    );
    expect(document.querySelector('.spread-layout')).toHaveClass('choice5');
    labels.forEach((label) => expect(screen.getByText(label, { exact: true })).toBeVisible());
  });
});

describe('synthetic tarot preview continuity', () => {
  it('keeps a single reveal separate from the all-reveal action', async () => {
    const view = render(<RevealSpread />);
    await userEvent.click(screen.getByRole('button', { name: '揭开第1张牌' }));
    expect(screen.getByRole('img', { name: '星币八正位' })).toBeVisible();
    expect(screen.getAllByRole('img', { name: '不透明的塔罗牌背' })).toHaveLength(2);
    view.rerender(<RevealSpread allRevealed />);
    expect(screen.getByRole('img', { name: '宝剑骑士逆位' })).toBeVisible();
    expect(screen.getByRole('img', { name: '星星正位' })).toBeVisible();
    expect(document.querySelectorAll('.tarot-flip')[2]).toHaveStyle('--tarot-reveal-delay: 180ms');
  });

  it.each([
    ['focus1', 1],
    ['reflect3', 3],
    ['choice5', 5],
  ] as const)('opens the %s reveal deep link with %i opaque backs', (spread, count) => {
    window.history.replaceState(null, '', `#/tarot?spread=${spread}&step=reveal`);
    render(<Tarot />);
    expect(screen.getAllByRole('img', { name: '不透明的塔罗牌背' })).toHaveLength(count);
    expect(screen.getByRole('button', { name: '揭牌' })).toHaveAttribute('aria-current', 'step');
  });

  it('opens the picker deep link with all 78 backs while the old default stays on interpretation', () => {
    window.history.replaceState(null, '', '#/tarot?spread=reflect3&step=pick');
    const view = render(<Tarot />);
    expect(screen.getByRole('group', { name: '亲手点选牌背' }).querySelectorAll('button')).toHaveLength(78);
    view.unmount();
    window.history.replaceState(null, '', '#/tarot');
    render(<Tarot />);
    expect(screen.getByRole('button', { name: '解读' })).toHaveAttribute('aria-current', 'step');
  });
});
