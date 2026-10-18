import { useRef, type KeyboardEvent } from 'react';
import { useReducedMotion } from 'motion/react';
import { Button } from '../components/ui/Controls';
import { image, type Draw } from './public';

export function ServerSpread({
  draw,
  busy,
  mutate,
}: {
  draw: Draw;
  busy: boolean;
  mutate: (action: 'select' | 'reveal', payload: Record<string, unknown>) => void;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const reduced = useReducedMotion();
  const picking =
    draw.draw_source === 'pick' && draw.cards.length < draw.spread.positions.length && draw.status !== 'cancelled';
  const cancelled = draw.status === 'cancelled';
  function move(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const candidates = refs.current.filter((button): button is HTMLButtonElement =>
      Boolean(button && !button.disabled),
    );
    const current = candidates.indexOf(refs.current[index]!);
    const columns = window.matchMedia('(min-width: 1024px)').matches ? 13 : 6;
    const offset = { ArrowRight: 1, ArrowLeft: -1, ArrowUp: -columns, ArrowDown: columns }[event.key];
    if (offset !== undefined || event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      const next =
        event.key === 'Home'
          ? 0
          : event.key === 'End'
            ? candidates.length - 1
            : (current + (offset ?? 0) + candidates.length) % candidates.length;
      candidates[next]?.focus();
    }
  }
  return (
    <div className="stack">
      {picking && (
        <section className="stack">
          <h3>
            选第{draw.cards.length + 1}张 · {draw.spread.positions[draw.cards.length]}
          </h3>
          <p className="meta">牌序已固定。按方向键移动，回车选牌；不能取消已保存的单张选择。</p>
          <p role="status">
            已选 {draw.cards.length} / {draw.spread.positions.length}
          </p>
          <div className="tarot-picker" role="group" aria-label="亲手点选牌背">
            {draw.backs.map((back, index) => (
              <button
                type="button"
                key={back.back_id}
                ref={(node) => {
                  refs.current[index] = node;
                }}
                disabled={busy || back.selected}
                aria-label={`第${index + 1}张牌背${back.selected ? '，已选择' : ''}`}
                aria-pressed={back.selected}
                onKeyDown={(e) => move(e, index)}
                onClick={() => mutate('select', { back_id: back.back_id })}>
                <img src="/static/tarot/back.svg" alt="" />
              </button>
            ))}
          </div>
        </section>
      )}
      <div
        className={`spread-layout ${draw.spread_id}`}
        role="group"
        aria-label="本次固定牌阵"
        data-reduced-motion={reduced ? 'true' : 'false'}>
        {draw.cards.map((position) => (
          <figure className="tarot-card" key={position.position}>
            <button
              type="button"
              className="flip-button"
              disabled={busy || position.revealed || cancelled || picking}
              aria-label={
                position.revealed
                  ? `${position.label}：${position.card?.name}，${position.orientation === 'reversed' ? '逆位' : '正位'}`
                  : `揭开第${position.position}张牌`
              }
              onClick={() => mutate('reveal', { position: position.position })}>
              <img
                src={position.revealed ? image(position.card?.card_id) : '/static/tarot/back.svg'}
                className={position.revealed && position.orientation === 'reversed' ? 'reversed' : ''}
                alt={
                  position.revealed
                    ? `${position.card?.name} · ${position.orientation === 'reversed' ? '逆位' : '正位'}`
                    : '不透明的塔罗牌背'
                }
              />
            </button>
            <figcaption>
              <p className="meta">{position.label}</p>
              {position.revealed && (
                <>
                  <h3 className="small-text">{position.card?.name}</h3>
                  <p className="small-text">
                    {position.orientation === 'reversed' ? position.card?.reversed : position.card?.upright}
                  </p>
                  <details>
                    <summary>牌意与反思问题</summary>
                    <p>{position.card?.misreading}</p>
                    <p>{position.card?.question}</p>
                  </details>
                </>
              )}
            </figcaption>
          </figure>
        ))}
      </div>
      {!picking && !cancelled && draw.cards.some((c) => !c.revealed) && (
        <Button disabled={busy} onClick={() => mutate('reveal', {})}>
          全部揭开 · 跳过动画
        </Button>
      )}
      {cancelled && <p role="status">这次选牌已结束，已有记录保留。</p>}
    </div>
  );
}
