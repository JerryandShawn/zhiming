import { useState } from 'react';
import { Button, Input, Segmented, Switch, Textarea } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { pendingPayload } from '../api/operations';
import { useResource } from '../api/useResource';
import { ManualCards, manualValid, type ManualCard } from './ManualCards';
import { list, object, text, type Deck, type Draw } from './public';

export function QuestionForm({
  deck,
  previous,
  busy,
  onSubmit,
}: {
  deck: Deck;
  previous?: Draw;
  busy: boolean;
  onSubmit: (payload: Record<string, unknown>) => void;
}) {
  const pending = object(pendingPayload('tarot:create'));
  const cases = useResource<unknown>('/api/cases');
  const caseOptions = list(cases.data).map((value) => ({
    value: text(object(value).id),
    label: text(object(value).title),
  }));
  const [question, setQuestion] = useState(text(pending.question) || previous?.question || '');
  const [background, setBackground] = useState(text(pending.background));
  const [spread, setSpread] = useState(text(pending.spread_id) || previous?.spread_id || 'reflect3');
  const [source, setSource] = useState(text(pending.draw_source) || previous?.draw_source || 'auto');
  const [reversals, setReversals] = useState(
    typeof pending.reversals === 'boolean' ? pending.reversals : (previous?.reversals ?? deck.reversals),
  );
  const [optionA, setA] = useState(text(object(pending.options).A) || previous?.options.A || '');
  const [optionB, setB] = useState(text(object(pending.options).B) || previous?.options.B || '');
  const linkedCase = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('case') ?? '';
  const [caseId, setCase] = useState(text(pending.case_id) || previous?.case_id || linkedCase);
  const [cards, setCards] = useState<ManualCard[]>(
    Array.isArray(pending.manual_cards) ? (pending.manual_cards as ManualCard[]) : [],
  );
  const positions = deck.spreads.find((s) => s.id === spread)?.positions ?? [];
  const choice = spread === 'choice5';
  const previousId = text(pending.previous_draw_id) || previous?.id;
  const explicit = pending.explicit_new === true || Boolean(previous);
  const invalid =
    !question.trim() ||
    !positions.length ||
    (choice && (!optionA.trim() || !optionB.trim() || optionA.trim() === optionB.trim())) ||
    (source === 'manual' && !manualValid(cards, positions.length));
  return (
    <form
      className="stack tarot-form"
      aria-label="塔罗提问"
      onSubmit={(event) => {
        event.preventDefault();
        if (invalid || busy) return;
        onSubmit({
          question: question.trim(),
          background: background.trim(),
          spread_id: spread,
          draw_source: source,
          reversals,
          subject_id: 'self',
          options: choice ? { A: optionA.trim(), B: optionB.trim() } : {},
          explicit_new: explicit,
          ...(caseId.trim() ? { case_id: caseId.trim() } : {}),
          ...(previousId ? { previous_draw_id: previousId } : {}),
          ...(source === 'manual'
            ? {
                manual_cards: cards.map((c) => ({
                  card_id: c.card_id,
                  orientation: reversals ? c.orientation : 'upright',
                })),
              }
            : {}),
        });
      }}>
      {explicit && <p className="meta">你已明确开始新一轮，原牌阵会保留并关联。</p>}
      {Object.keys(pending).length > 0 && <p role="status">上次保存未确认，已恢复原请求草稿；重试会沿用同一标识。</p>}
      <label className="field">
        想问什么？
        <Textarea required maxLength={2000} value={question} onChange={(e) => setQuestion(e.target.value)} />
      </label>
      <div className="field">
        <span>牌阵</span>
        <Select
          label="牌阵"
          value={spread}
          options={deck.spreads.map((s) => ({ value: s.id, label: `${s.name} · ${s.positions.length}张` }))}
          onChange={(next) => {
            setSpread(next);
            setCards([]);
          }}
        />
      </div>
      <Segmented
        label="抽法"
        value={source}
        onChange={setSource}
        options={[
          { value: 'auto', label: '服务端随机' },
          { value: 'pick', label: '亲手点选' },
          { value: 'manual', label: '录入实体牌' },
        ]}
      />
      <div className="setting-row">
        <span>含逆位</span>
        <Switch label="含逆位" checked={reversals} onChange={setReversals} />
      </div>
      {choice && (
        <>
          <label className="field">
            选项A
            <Input required maxLength={1200} value={optionA} onChange={(e) => setA(e.target.value)} />
          </label>
          <label className="field">
            选项B
            <Input required maxLength={1200} value={optionB} onChange={(e) => setB(e.target.value)} />
          </label>
          {optionA.trim() && optionA.trim() === optionB.trim() && (
            <p className="field-error">A与B需要是两个不同的选项</p>
          )}
        </>
      )}
      <details className="disclosure">
        <summary>背景与关联事项</summary>
        <div className="disclosure-content stack">
          <label className="field">
            背景补充
            <Textarea maxLength={4000} value={background} onChange={(e) => setBackground(e.target.value)} />
          </label>
          <div className="field">
            <span>关联事项</span>
            <Select
              label="关联事项"
              value={caseId}
              onChange={setCase}
              options={[
                { value: '', label: '新建事项' },
                ...caseOptions,
                ...(caseId && !caseOptions.some((option) => option.value === caseId)
                  ? [{ value: caseId, label: '原关联事项（待核对）' }]
                  : []),
              ]}
            />
          </div>
          {cases.isError && <Button onClick={() => void cases.refetch()}>重新读取事项列表</Button>}
          <p className="meta">留空时由服务器为这次问题建立事项；关联已有事项时沿用其固定牌阵。</p>
        </div>
      </details>
      {source === 'manual' && (
        <ManualCards positions={positions} cards={deck.cards} reversals={reversals} value={cards} onChange={setCards} />
      )}
      <Button type="submit" variant="primary" disabled={invalid} loading={busy}>
        {source === 'manual' ? '保存实体牌记录' : source === 'pick' ? '准备牌背，开始选牌' : '开始梳理'}
      </Button>
      <p className="meta">牌由服务器固定保存。解释重试不会重新抽牌；象征解释供反思，请结合现实信息判断。</p>
    </form>
  );
}
