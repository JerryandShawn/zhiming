import { useEffect, useId, useRef, useState } from 'react';
import { Button, Disclosure } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { usePanelHistory } from '../usePanelHistory';
import { LearningCards } from './LearningCards';
import { StudyEvidenceSheet } from './StudyEvidenceSheet';
import { systemLabels } from './labels';
import { useStudyRead } from './useStudyRead';
import type { LearningSample, LearningSystem, StudyEvidenceRef, StudyMetadata, StudyPort } from './types';

export function LearningPanel({ port, metadata }: { port?: StudyPort; metadata?: StudyMetadata }) {
  const [selected, setSelected] = useState('ayuan-bazi');
  const reader = useStudyRead<LearningSample>(port, selected);
  const [evidence, setEvidence] = useState<{ owner: typeof reader.owner; reference: StudyEvidenceRef }>();
  const [notice, setNotice] = useState('');
  const returnTo = useRef<HTMLButtonElement>();
  const { open: panelOpen, onOpenChange } = usePanelHistory();
  const contentId = useId();
  const run = reader.run;
  const read = () => reader.run((scope, signal) => scope.readLearning(selected, signal));
  useEffect(() => {
    void run((scope, signal) => scope.readLearning(selected, signal));
  }, [run, selected]);
  const sample =
    reader.view.status === 'ready' && reader.view.value.sample_id === selected ? reader.view.value : undefined;
  const item =
    evidence?.owner === reader.owner && sample && evidence.reference.sample_id === sample.sample_id
      ? reader.resolveEvidence(evidence.reference)
      : undefined;
  const related =
    item?.evidence_refs?.map((reference) => reader.resolveEvidence({ sample_id: selected, ...reference })) ?? [];
  useEffect(() => {
    if (evidence && (!item || evidence.owner !== reader.owner)) {
      onOpenChange(false);
      setEvidence(undefined);
    }
  }, [item, evidence, reader.owner, onOpenChange]);
  const choices: { sample_id: string; system: LearningSystem; card_count?: number }[] = metadata?.learning ?? [
    { sample_id: 'ayuan-bazi', system: 'bazi' },
    { sample_id: 'ayuan-ziwei', system: 'ziwei' },
    { sample_id: 'ayuan-astro', system: 'astro' },
  ];
  return (
    <section className="study-panel stack" aria-label="学习卡">
      <header className="stack small">
        <h3 id="study-learning-heading" tabIndex={-1}>
          从合成盘面练读法
        </h3>
        <p className="secondary-text">
          阿远的公开合成样例。先读实际返回的条件与口径，不把条件命中当作格局成立或现实结果。
        </p>
      </header>
      <div className="field">
        学习卡体系
        <Select
          label="学习卡体系"
          value={selected}
          options={choices.map((choice) => ({
            value: choice.sample_id,
            label: `${systemLabels[choice.system]}${choice.card_count === undefined ? '样例' : ` · ${choice.card_count}张`}`,
          }))}
          onChange={(value) => {
            setSelected(value);
            setNotice('');
          }}
        />
      </div>
      {!port && <p className="meta">学习资料尚未载入；不读取个人档案或临时排盘。</p>}
      {reader.view.status === 'loading' && <p role="status">正在读取当前体系的学习卡…</p>}
      {reader.view.status === 'error' && (
        <div role="alert" className="study-read-error stack small">
          <p>这份学习样例暂时没有展开。体系选择仍保留。</p>
          <Button onClick={() => void read()}>重新读取学习卡</Button>
        </div>
      )}
      {reader.view.status === 'unavailable' && <p role="status">{reader.view.message}</p>}
      {reader.view.status === 'ready' && !sample && (
        <p role="alert">这份样例的归属尚未通过核对，请重新读取当前体系。</p>
      )}
      {notice && <p role="status">{notice}</p>}
      {sample && (
        <div data-learning-sample={sample.sample_id} className="stack">
          <p className="meta">
            {systemLabels[sample.system]} · {sample.cards.length}张学习卡 · 只读公开样例
          </p>
          <LearningCards
            sample={sample}
            openEvidence={(reference, origin) => {
              if (!reader.resolveEvidence(reference)) {
                setNotice('这条依据暂不可用，请重新读取当前样例。');
                return;
              }
              returnTo.current = origin;
              setEvidence({ owner: reader.owner, reference });
              onOpenChange(true);
            }}
          />
          <Disclosure title="这份样例的限制">
            <ul className="study-limit-list small-text secondary-text">
              {sample.limits.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          </Disclosure>
        </div>
      )}
      <p className="meta">个人学习进度尚未接入；不会把浏览记录写入记忆、档案或设备存储。</p>
      <StudyEvidenceSheet
        item={item}
        related={related}
        open={panelOpen && Boolean(item)}
        onOpenChange={onOpenChange}
        returnTo={returnTo}
        contentId={contentId}
      />
    </section>
  );
}
