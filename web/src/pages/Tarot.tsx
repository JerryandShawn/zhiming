import { useState } from 'react';
import { Layers } from 'lucide-react';
import { AssistantMessage } from '../components/Messages';
import { CardPicker, RevealSpread, SpreadLayout } from '../components/TarotCards';
import { spreadCounts, spreadNames, type TarotDraft, type SpreadKind } from '../components/TarotDraft';
import { Button, Disclosure, Input, Segmented, Switch, Textarea } from '../components/ui/Controls';

function QuestionForm({
  draft,
  onChange,
  onNext,
}: {
  draft: TarotDraft;
  onChange: (draft: TarotDraft) => void;
  onNext: () => void;
}) {
  const { spread, method, reverse, question, optionA, optionB } = draft;
  const invalid = spread === 'choice5' && (!optionA.trim() || !optionB.trim() || optionA.trim() === optionB.trim());
  return (
    <form
      className="stack tarot-form"
      onSubmit={(event) => {
        event.preventDefault();
        onNext();
      }}>
      <label className="field">
        想问什么？
        <Textarea
          required
          value={question}
          onChange={(event) => onChange({ ...draft, question: event.target.value })}
        />
      </label>
      <div className="spread-choices">
        {[
          ['focus1', '看一件事', 1],
          ['reflect3', '梳理问题', 3],
          ['choice5', 'A/B选择', 5],
        ].map(([value, label, count]) => (
          <button
            className="spread-choice"
            type="button"
            aria-pressed={spread === value}
            key={value}
            onClick={() => onChange({ ...draft, spread: value as SpreadKind })}>
            <span className="spread-mini" aria-hidden="true">
              {Array.from({ length: Number(count) }, (_, index) => (
                <span key={index} />
              ))}
            </span>
            <span className="small-text">{label}</span>
            <span className="meta">{count}张</span>
          </button>
        ))}
      </div>
      <Segmented
        label="抽法"
        options={['随机', '亲手点选', '录入实体牌'].map((value) => ({ value, label: value }))}
        value={method}
        onChange={(method) => onChange({ ...draft, method })}
      />
      <div className="setting-row">
        <span>含逆位</span>
        <Switch label="含逆位" checked={reverse} onChange={(reverse) => onChange({ ...draft, reverse })} />
      </div>
      {spread === 'choice5' && (
        <>
          <label className="field">
            选项A
            <Input value={optionA} onChange={(event) => onChange({ ...draft, optionA: event.target.value })} />
          </label>
          <label className="field">
            选项B
            <Input
              value={optionB}
              onChange={(event) => onChange({ ...draft, optionB: event.target.value })}
              aria-invalid={invalid}
            />
          </label>
          {invalid && <p className="field-error">A与B需要是两个不同的选项</p>}
        </>
      )}
      <Disclosure title="高级设置" count="背景补充、关联事项">
        <label className="field">
          背景补充
          <Textarea />
        </label>
      </Disclosure>
      <Button type="submit" variant="primary" disabled={!question.trim() || invalid}>
        开始（合成示例）
      </Button>
    </form>
  );
}

export default function Tarot() {
  const [step, setStep] = useState('解读');
  const [revealed, reveal] = useState(false);
  const [version, setVersion] = useState('v1');
  const [draft, setDraft] = useState<TarotDraft>({
    spread: 'reflect3',
    method: '随机',
    reverse: true,
    question: '这次面试我该注意什么？',
    optionA: '',
    optionB: '',
  });
  const [selected, setSelected] = useState<number[]>([]);
  const count = spreadCounts[draft.spread];
  return (
    <div className="page" data-page="tarot">
      <header className="page-heading row between">
        <h1>塔罗</h1>
        <Button variant="ghost" onClick={() => setStep('提问')}>
          <Layers className="icon" />
          新问题
        </Button>
      </header>
      <nav className="tarot-steps" aria-label="抽牌步骤">
        {['提问', '选牌', '揭牌', '解读'].map((name) => (
          <button
            key={name}
            type="button"
            aria-current={step === name ? 'step' : undefined}
            onClick={() => setStep(name)}>
            {name}
          </button>
        ))}
      </nav>
      {step === '提问' ? (
        <QuestionForm
          draft={draft}
          onChange={setDraft}
          onNext={() => {
            setSelected([]);
            reveal(false);
            setStep('选牌');
          }}
        />
      ) : step === '选牌' ? (
        <div className="stack">
          <h2>{draft.question}</h2>
          <p className="meta">
            {spreadNames[draft.spread]} · {count}张 · 抽法偏好：{draft.method}
          </p>
          <p className="small-text">本地合成演示统一使用牌背点选，不执行真实随机或实体牌录入。</p>
          <CardPicker count={count} selected={selected} onChange={setSelected} />
          <Button disabled={selected.length !== count} onClick={() => setStep('揭牌')}>
            查看合成牌阵
          </Button>
        </div>
      ) : step === '揭牌' ? (
        <div className="stack">
          <h2>{draft.question}</h2>
          <p className="meta">
            {spreadNames[draft.spread]} · {count}张
          </p>
          <RevealSpread allRevealed={revealed} layout={draft.spread} reverse={draft.reverse} />
          <Button variant="primary" onClick={() => reveal(true)}>
            全部揭开
          </Button>
          {revealed && <Button onClick={() => setStep('解读')}>看解读</Button>}
        </div>
      ) : (
        <div className="page-grid">
          <div>
            <h2>{draft.question}</h2>
            <p className="meta">
              {spreadNames[draft.spread]} · {count}张 · {draft.reverse ? '含逆位' : '仅正位'} · 10月17日
            </p>
            {draft.spread === 'choice5' && (
              <p className="small-text">
                A：{draft.optionA}；B：{draft.optionB}
              </p>
            )}
            {selected.length > 0 && (
              <p className="meta">
                本地已选序号：{selected.map((index) => index + 1).join('、')}；牌面为固定合成样例。
              </p>
            )}
            <SpreadLayout layout={draft.spread} reverse={draft.reverse} />
            <AssistantMessage time="10:42">
              <p>
                {draft.question === '这次面试我该注意什么？' && draft.spread === 'reflect3'
                  ? '这三张连起来看：你过去在专业上下过扎实的功夫。现在要留意的是节奏，别急着一口气把话说完。慢一点，让对方看见你已经做过的事。'
                  : `这是“${draft.question}”的${count}张合成排版示例，没有生成针对问题的真实解读。请把牌面当作反思提示，结合现实信息判断。`}
              </p>
            </AssistantMessage>
            <Disclosure title="每张牌" count={`${count}张 · 合成样例`}>
              <p className="small-text">
                固定样例牌面用于检查当前牌阵的布局、正逆位和揭牌状态，不生成针对问题的分析，不替代现实判断。
              </p>
            </Disclosure>
            <div className="row wrap">
              <Button onClick={() => setVersion(version === 'v1' ? 'v2' : 'v1')}>解读版本 {version}</Button>
              <Button variant="ghost" onClick={() => setStep('提问')}>
                补充背景再解读
              </Button>
              <a href="#/chat" className="button ghost">
                带去对话
              </a>
            </div>
          </div>
          <aside className="tarot-history">
            <h2>以前问过的</h2>
            <div className="list-row">
              <p>怎样安排下周的准备？</p>
              <p className="meta">梳理问题 · 10月15日</p>
            </div>
            <p className="meta">合成牌阵固定展示，不会再次抽牌。</p>
          </aside>
        </div>
      )}
    </div>
  );
}
