import { useState } from 'react';
import { Button, Textarea } from '../components/ui/Controls';
import { ManualCards, manualValid, type ManualCard } from './ManualCards';
import { ServerSpread } from './ServerSpread';
import { ReadingPanel } from './ReadingPanel';
import { pendingPayload } from '../api/operations';
import { list, object, text, type Deck, type Draw, type Reading } from './public';

export function DrawPanel({
  draw,
  deck,
  busy,
  versions,
  onChangeVersions,
  mutate,
  newRound,
  onReadingBusy,
}: {
  draw: Draw;
  deck: Deck;
  busy: boolean;
  versions: Reading[];
  onChangeVersions: (value: Reading[]) => void;
  mutate: (action: 'select' | 'reveal' | 'cancel' | 'manual', payload: Record<string, unknown>) => void;
  newRound: () => void;
  onReadingBusy: (value: boolean) => void;
}) {
  const manualPending = object(pendingPayload(`tarot:${draw.id}:manual`));
  const frozenCards = () =>
    list(manualPending.cards).map((value) => ({
      card_id: text(object(value).card_id),
      orientation: text(object(value).orientation),
    }));
  const [correcting, setCorrecting] = useState(Object.keys(manualPending).length > 0);
  const [reason, setReason] = useState(text(manualPending.reason));
  const [cards, setCards] = useState<ManualCard[]>(frozenCards);
  const pendingActions = (['select', 'reveal', 'cancel', 'manual'] as const).flatMap((action) => {
    const payload = pendingPayload<Record<string, unknown>>(`tarot:${draw.id}:${action}`);
    return payload ? [{ action, payload }] : [];
  });
  return (
    <div className="stack">
      <header>
        <h2>{draw.question}</h2>
        <p className="meta">
          {draw.spread.name} · {draw.reversals ? '含逆位' : '仅正位'} · {draw.created_at.slice(0, 10)} · 第
          {draw.revision}次录入
        </p>
      </header>
      {draw.options.A && (
        <div className="panel" aria-label="冻结的A/B选项">
          <p>A：{draw.options.A}</p>
          <p>B：{draw.options.B}</p>
          <p className="meta">选项已随本次牌阵冻结。</p>
        </div>
      )}
      {draw.previous_draw_id && (
        <a className="text-link" href={`#/tarot?draw=${encodeURIComponent(draw.previous_draw_id)}`}>
          查看关联的上一轮或录入版本
        </a>
      )}
      {pendingActions.length > 0 && (
        <section className="stack" aria-label="未确认的牌阵操作">
          <p className="meta">上次操作尚未收到确认。先用原请求核对回执，再继续下一步。</p>
          {pendingActions.map(({ action, payload }) => (
            <Button key={action} disabled={busy} onClick={() => mutate(action, payload)}>
              重试未确认的{{ select: '选牌', reveal: '揭牌', cancel: '取消', manual: '实体牌更正' }[action]}
            </Button>
          ))}
        </section>
      )}
      <ServerSpread draw={draw} busy={busy} mutate={mutate} />
      {draw.status === 'ready' && (
        <ReadingPanel
          key={draw.id}
          drawId={draw.id}
          versions={versions}
          onChange={onChangeVersions}
          onBusy={onReadingBusy}
        />
      )}
      <div className="row wrap">
        <a
          className="button ghost"
          href={`#/chat?case=${encodeURIComponent(draw.case_id)}${draw.status === 'ready' ? `&draw=${encodeURIComponent(draw.id)}` : ''}`}>
          带去对话
        </a>
        <Button disabled={busy} onClick={newRound}>
          明确开始新一轮
        </Button>
        {!['ready', 'cancelled'].includes(draw.status) && (
          <Button disabled={busy} onClick={() => mutate('cancel', {})}>
            结束这次选牌
          </Button>
        )}
        {draw.draw_source === 'manual' && (
          <Button
            disabled={busy}
            onClick={() => {
              setCorrecting(!correcting);
              setCards(
                Object.keys(manualPending).length
                  ? frozenCards()
                  : draw.cards.map((p) => ({
                      card_id: p.card?.card_id ?? '',
                      orientation: p.orientation ?? 'upright',
                    })),
              );
            }}>
            更正实体牌录入
          </Button>
        )}
      </div>
      {correcting && (
        <form
          className="stack"
          aria-label="更正实体牌录入"
          onSubmit={(e) => {
            e.preventDefault();
            if (manualValid(cards, draw.spread.positions.length) && reason.trim())
              mutate('manual', { cards, reason: reason.trim() });
          }}>
          <p className="meta">仅修正实体牌录入错误；服务器保留旧版本，更正后重新揭牌和解读。</p>
          <ManualCards
            positions={draw.spread.positions}
            cards={deck.cards}
            reversals={draw.reversals}
            value={cards}
            onChange={setCards}
          />
          <label className="field">
            更正原因
            <Textarea required maxLength={800} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <Button type="submit" disabled={busy || !reason.trim() || !manualValid(cards, draw.spread.positions.length)}>
            保存录入更正
          </Button>
        </form>
      )}
    </div>
  );
}
