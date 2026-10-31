import { useEffect, useState } from 'react';
import { Button, Input } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { useStudyTerms } from './StudyTerms';
import { systemLabels } from './labels';
import { useStudyRead } from './useStudyRead';
import type { StudyMetadata, StudyPort, StudySystem, TermSummary } from './types';

const describeTerm = (term: TermSummary) =>
  `${systemLabels[term.system]}${term.aliases.length ? ` · ${term.aliases.join('、')}` : ''}`;

export function GlossaryPanel({ port, metadata }: { port?: StudyPort; metadata?: StudyMetadata }) {
  const [text, setText] = useState(''),
    [system, setSystem] = useState<StudySystem | 'all'>('all');
  const [visible, setVisible] = useState(12);
  const reader = useStudyRead<TermSummary[]>(port, JSON.stringify([text, system]));
  const terms = useStudyTerms();
  const run = reader.run;
  const read = () =>
    reader.run((scope, signal) => scope.search({ text, system: system === 'all' ? undefined : system }, signal));
  useEffect(() => {
    void run((scope, signal) => scope.search({ text, system: system === 'all' ? undefined : system }, signal));
  }, [run, text, system]);
  const rows = reader.view.status === 'ready' ? reader.view.value : undefined;
  return (
    <section className="study-panel stack" aria-label="术语词典">
      <header className="stack small">
        <h3>把术语说清楚</h3>
        <p className="secondary-text">按词名、别名或解释查找。点开词条，连同例句、出处范围和流派差异一起读。</p>
      </header>
      <div className="study-search-grid">
        <label className="field">
          搜索术语
          <Input
            type="search"
            value={text}
            maxLength={1000}
            placeholder="如：日主、命宫、上升点…"
            onChange={(event) => {
              setText(event.target.value);
              setVisible(12);
            }}
          />
        </label>
        <div className="field">
          术语体系
          <Select
            label="术语体系"
            value={system}
            options={[
              { value: 'all', label: '全部体系' },
              ...Object.entries(systemLabels).map(([value, label]) => ({ value, label })),
            ]}
            onChange={(value) => {
              setSystem(value as StudySystem | 'all');
              setVisible(12);
            }}
          />
        </div>
      </div>
      {!port && <p className="meta">词典资料载入后会显示结果，你可以先保留搜索条件。</p>}
      {reader.view.status === 'loading' && <p role="status">正在检索术语…</p>}
      {reader.view.status === 'error' && (
        <div role="alert" className="study-read-error stack small">
          <p>这次检索没有完成，搜索条件仍保留。</p>
          <Button onClick={() => void read()}>重新检索</Button>
        </div>
      )}
      {reader.view.status === 'unavailable' && <p role="status">{reader.view.message}</p>}
      {rows && (
        <p className="meta" role="status">
          找到 {rows.length} 条{system === 'all' ? '术语' : systemLabels[system] + '术语'}
          {rows.length > visible ? `，先显示前${visible}条` : ''}。
        </p>
      )}
      {rows?.length === 0 && (
        <p className="study-empty">还没有匹配的词条。可以缩短关键词，或切到全部体系；不会临时编造释义。</p>
      )}
      {rows && rows.length > 0 && (
        <ul className="study-term-list" aria-label="术语检索结果">
          {rows.slice(0, visible).map((term) => (
            <li key={term.term_id}>
              <Button
                variant="ghost"
                className="study-term-row"
                aria-label={`查看术语：${term.term} ${describeTerm(term)}`}
                disabled={!terms}
                onClick={(event) => terms?.openTerm(term.term_id, event.currentTarget)}>
                <span className="study-term-name">{term.term}</span>
                <span className="meta">{describeTerm(term)}</span>
              </Button>
            </li>
          ))}
        </ul>
      )}
      {rows && rows.length > visible && <Button onClick={() => setVisible((value) => value + 12)}>再看12条</Button>}
      {metadata && (
        <p className="meta">
          共{metadata.glossary.entry_count}条术语、{metadata.glossary.source_count}
          处登记出处。词典为研习草稿，来源说明和待核项保留在详情中。
        </p>
      )}
    </section>
  );
}
