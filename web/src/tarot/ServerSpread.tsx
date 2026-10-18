import { useEffect, useRef, useState } from 'react';
import { Button, Tag } from '../components/ui/Controls';
import { image, type Draw } from './public';
import { CardBackGrid } from './CardBackGrid';
import { FlipFace } from './FlipFace';
import { useTarotReducedMotion } from './useTarotMotion';

export function ServerSpread({
  draw,
  busy,
  mutate,
}: {
  draw: Draw;
  busy: boolean;
  mutate: (action: 'select' | 'reveal', payload: Record<string, unknown>) => void;
}) {
  const group = useRef<HTMLDivElement>(null);
  const [batchReveal, setBatchReveal] = useState(false);
  const pendingReveal = useRef<number | 'all' | null>(null);
  const reduced = useTarotReducedMotion();
  const picking =
    draw.draw_source === 'pick' && draw.cards.length < draw.spread.positions.length && draw.status !== 'cancelled';
  const cancelled = draw.status === 'cancelled';
  const wasPicking = useRef(picking);
  useEffect(() => {
    if (wasPicking.current && !picking) group.current?.focus();
    wasPicking.current = picking;
  }, [picking]);
  useEffect(() => {
    if (busy || pendingReveal.current === null) return;
    const requested = pendingReveal.current;
    pendingReveal.current = null;
    const buttons = Array.from(group.current?.querySelectorAll<HTMLButtonElement>('.flip-button') ?? []);
    const previous = requested === 'all' ? -1 : draw.cards.findIndex((position) => position.position === requested);
    const unconfirmed = buttons[previous];
    const next = unconfirmed && !unconfirmed.disabled ? unconfirmed : buttons.find((button) => !button.disabled);
    if (next) next.focus();
    else group.current?.focus();
  }, [busy, draw.cards]);
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
          <CardBackGrid
            backs={draw.backs.map((back, index) => ({
              id: back.back_id,
              label: `第${index + 1}张牌背${back.selected ? '，已选择' : ''}`,
              selected: back.selected,
            }))}
            disabled={busy}
            onSelect={(id) => mutate('select', { back_id: id })}
          />
        </section>
      )}
      <div
        className={`spread-layout ${draw.spread_id}`}
        ref={group}
        tabIndex={-1}
        role="group"
        aria-label="本次固定牌阵"
        data-reduced-motion={reduced ? 'true' : 'false'}>
        {draw.cards.map((position, index) => (
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
              onClick={() => {
                pendingReveal.current = position.position;
                setBatchReveal(false);
                mutate('reveal', { position: position.position });
              }}>
              <FlipFace
                revealed={position.revealed}
                frontImage={position.revealed ? image(position.card?.card_id) : undefined}
                reversed={position.orientation === 'reversed'}
                delay={batchReveal ? index * 90 : 0}
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
                  {position.orientation === 'reversed' && <Tag tone="work">逆位</Tag>}
                </>
              )}
            </figcaption>
          </figure>
        ))}
      </div>
      {!picking && !cancelled && draw.cards.some((c) => !c.revealed) && (
        <Button
          disabled={busy}
          onClick={() => {
            pendingReveal.current = 'all';
            setBatchReveal(true);
            mutate('reveal', {});
          }}>
          {reduced ? '全部揭开 · 跳过动画' : '全部揭开'}
        </Button>
      )}
      {draw.cards.some((position) => position.revealed) && (
        <section className="stack small" aria-label="每张牌的牌意与反思问题">
          {draw.cards
            .filter((position) => position.revealed)
            .map((position) => (
              <details className="disclosure" key={position.position}>
                <summary>
                  {position.label} · {position.card?.name} · {position.orientation === 'reversed' ? '逆位' : '正位'}
                </summary>
                <div className="disclosure-content">
                  <p>{position.orientation === 'reversed' ? position.card?.reversed : position.card?.upright}</p>
                  <p>{position.card?.misreading}</p>
                  <p>{position.card?.question}</p>
                </div>
              </details>
            ))}
        </section>
      )}
      {cancelled && <p role="status">这次选牌已结束，已有记录保留。</p>}
    </div>
  );
}
