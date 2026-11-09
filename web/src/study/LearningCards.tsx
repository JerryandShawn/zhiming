import { Button, Tag } from '../components/ui/Controls';
import { kindLabels } from './labels';
import type { LearningSample, StudyEvidenceRef } from './types';

export function LearningCards({
  sample,
  openEvidence,
}: {
  sample: LearningSample;
  openEvidence: (reference: StudyEvidenceRef, origin: HTMLButtonElement) => void;
}) {
  return (
    <div className="study-learning-cards stack">
      {sample.cards.map((card) => (
        <article className="study-learning-card stack small" key={card.point_id} data-learning-point={card.point_id}>
          <div className="row wrap">
            <Tag>{kindLabels[card.kind]}</Tag>
            <h4>{card.title}</h4>
          </div>
          <p>{card.text}</p>
          <p className="meta">读法与流派：{card.school}</p>
          <ul className="study-limit-list small-text secondary-text">
            {card.limits.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
          <div className="row wrap" aria-label={`${card.title}的计算依据`}>
            {card.evidence_refs.map((reference) => (
              <Button
                key={`${reference.document_id}:${reference.alias}:${reference.claim_id}`}
                variant="ghost"
                onClick={(event) => openEvidence({ sample_id: sample.sample_id, ...reference }, event.currentTarget)}>
                依据〔{reference.alias}〕
              </Button>
            ))}
            {!card.evidence_refs.length && <p className="meta">此卡没有可展开的计算依据。</p>}
          </div>
          <details className="disclosure">
            <summary>本卡出处</summary>
            <ul className="study-source-list">
              {card.sources.map((source, index) => (
                <li key={`${source.title}:${index}`}>
                  <p>{source.title}</p>
                  <p className="meta">{source.status}</p>
                  {source.locator && <p className="meta">定位：{source.locator}</p>}
                </li>
              ))}
            </ul>
          </details>
        </article>
      ))}
      {!sample.cards.length && <p className="study-empty">这份样例还没有足够的学习依据，不补造卡片。</p>}
    </div>
  );
}
