import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { nextBackIndex } from './keyboard';

type Back = { id: string; label: string; selected: boolean };

export function CardBackGrid({
  backs,
  disabled = false,
  complete = false,
  backImage = '/static/tarot/back.svg',
  onSelect,
}: {
  backs: Back[];
  disabled?: boolean;
  complete?: boolean;
  backImage?: string;
  onSelect: (id: string) => void;
}) {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const group = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef<number | null>(null);
  const locked = backs.map((back) => back.selected || disabled || complete);
  const tabIndex = locked[active] ? locked.findIndex((value) => !value) : active;

  useEffect(() => {
    if (disabled || pendingFocus.current === null) return;
    const previous = pendingFocus.current;
    pendingFocus.current = null;
    const saved = backs[previous]?.selected;
    const next = saved
      ? nextBackIndex(
          previous,
          'ArrowRight',
          1,
          backs.map((back) => back.selected),
        )
      : previous;
    const available = refs.current[next];
    if (available && !available.disabled) available.focus();
    else group.current?.focus();
    // A receipt or a failed pending write restores keyboard access without another request.
  }, [disabled, complete, backs]);

  function move(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (!['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const columns = window.matchMedia('(min-width: 1024px)').matches ? 13 : 6;
    const next = nextBackIndex(index, event.key, columns, locked);
    if (next >= 0) refs.current[next]?.focus();
  }

  return (
    <div className="tarot-picker" role="group" aria-label="亲手点选牌背" tabIndex={-1} ref={group}>
      {backs.map((back, index) => (
        <button
          type="button"
          key={back.id}
          ref={(element) => {
            refs.current[index] = element;
          }}
          disabled={locked[index]}
          tabIndex={tabIndex === index ? 0 : -1}
          aria-label={back.label}
          aria-pressed={back.selected}
          onFocus={() => setActive(index)}
          onKeyDown={(event) => move(event, index)}
          onClick={() => {
            pendingFocus.current = index;
            onSelect(back.id);
          }}>
          <img src={backImage} alt="" />
        </button>
      ))}
    </div>
  );
}
