import { useRef, useState, type KeyboardEvent } from 'react';
import back from '../../../static/tarot/back.svg';
import pentacles from '../../../static/tarot/pentacles-08.svg';
import swords from '../../../static/tarot/swords-12.svg';
import star from '../../../static/tarot/major-17.svg';
import world from '../../../static/tarot/major-21.svg';
import cups from '../../../static/tarot/cups-01.svg';
import { Button, Tag } from './ui/Controls';
import { spreadCounts, type SpreadKind } from './TarotDraft';

const cards = [
  { name: '星币八', image: pentacles, position: '过去的影响', reversed: false },
  { name: '宝剑骑士', image: swords, position: '现在的状态', reversed: true },
  { name: '星星', image: star, position: '可以怎么做', reversed: false },
  { name: '世界', image: world, position: 'A走向', reversed: false },
  { name: '圣杯一', image: cups, position: 'B走向', reversed: false },
];

export function SpreadLayout({
  faceUp = true,
  layout = 'reflect3',
  reverse = true,
}: {
  faceUp?: boolean;
  layout?: SpreadKind;
  reverse?: boolean;
}) {
  const count = spreadCounts[layout];
  return (
    <div className={`spread-layout ${layout}`}>
      {Array.from({ length: count }, (_, index) => {
        const card = cards[index % cards.length];
        return (
          <figure className="tarot-card" key={index}>
            <img
              className={faceUp && reverse && card.reversed ? 'reversed' : ''}
              src={faceUp ? card.image : back}
              alt={faceUp ? `${card.name}${reverse && card.reversed ? '逆位' : '正位'}` : '不透明的塔罗牌背'}
            />
            <figcaption>
              <p className="meta">{count === 5 ? ['现状', '选A', '选B', 'A走向', 'B走向'][index] : card.position}</p>
              {faceUp && (
                <>
                  <p className="small-text">
                    <strong>{card.name}</strong>
                  </p>
                  {reverse && card.reversed && <Tag tone="work">逆位</Tag>}
                </>
              )}
            </figcaption>
          </figure>
        );
      })}
    </div>
  );
}

export function CardPicker({
  count = 3,
  selected: controlled,
  onChange,
}: {
  count?: number;
  selected?: number[];
  onChange?: (selected: number[]) => void;
}) {
  const [local, setLocal] = useState<number[]>([]);
  const selected = controlled ?? local;
  const setSelected = onChange ?? setLocal;
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  function move(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const columns = window.matchMedia('(min-width: 1024px)').matches ? 13 : 6;
    const offset = { ArrowRight: 1, ArrowLeft: -1, ArrowUp: -columns, ArrowDown: columns }[event.key];
    if (offset) {
      event.preventDefault();
      refs.current[Math.max(0, Math.min(77, index + offset))]?.focus();
    }
  }
  return (
    <div className="stack">
      <p role="status">
        已选 {selected.length} / {count}
      </p>
      <div className="tarot-picker" role="group" aria-label="亲手点选牌背">
        {Array.from({ length: 78 }, (_, index) => (
          <button
            type="button"
            key={index}
            ref={(element) => {
              refs.current[index] = element;
            }}
            aria-label={`第${index + 1}张牌`}
            aria-pressed={selected.includes(index)}
            onKeyDown={(event) => move(event, index)}
            onClick={() => {
              if (!selected.includes(index) && selected.length < count) setSelected([...selected, index]);
            }}>
            <img src={back} alt="" />
          </button>
        ))}
      </div>
      <Button onClick={() => setSelected([])}>重新选择（示例）</Button>
    </div>
  );
}

export function RevealSpread({
  allRevealed = false,
  layout = 'reflect3',
  reverse = true,
}: {
  allRevealed?: boolean;
  layout?: SpreadKind;
  reverse?: boolean;
}) {
  const [opened, setOpened] = useState<number[]>([]);
  return (
    <div className={`spread-layout ${layout}`}>
      {cards.slice(0, spreadCounts[layout]).map((card, index) => {
        const visible = allRevealed || opened.includes(index);
        return (
          <figure className="tarot-card" key={card.name}>
            <button
              type="button"
              className={`flip-button ${visible ? 'revealed' : ''}`}
              aria-label={visible ? `${card.name}已揭开` : `揭开第${index + 1}张牌`}
              onClick={() => setOpened([...opened, index])}>
              {!visible && <img src={back} alt="不透明的塔罗牌背" />}
              {visible && (
                <img
                  className={`flip-front ${reverse && card.reversed ? 'reversed' : ''}`}
                  src={card.image}
                  alt={`${card.name}${reverse && card.reversed ? '逆位' : '正位'}`}
                />
              )}
            </button>
            <figcaption>
              <p className="meta">
                {layout === 'choice5' ? ['现状', '选A', '选B', 'A走向', 'B走向'][index] : card.position}
              </p>
              {visible && <p className="small-text">{card.name}</p>}
            </figcaption>
          </figure>
        );
      })}
    </div>
  );
}
