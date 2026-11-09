import type { RefObject } from 'react';
import DialogContent from '../components/ui/DialogContent';
import { basisLabels } from './labels';
import type { LearningEvidence } from './types';

function EvidenceBody({ item }: { item: LearningEvidence }) {
  return (
    <div className="stack small">
      <p>{item.summary}</p>
      <p className="meta">依据口径：{basisLabels[item.basis]}</p>
      {item.school && <p>读法与流派：{item.school}</p>}
      {item.sources?.map((source, index) => (
        <section className="stack small study-source" key={`${source.title}:${index}`}>
          <h3>{source.title}</h3>
          <p className="meta">{source.status}</p>
          {source.locator && <p className="meta">定位：{source.locator}</p>}
        </section>
      ))}
    </div>
  );
}

export function StudyEvidenceSheet({
  item,
  related,
  open,
  onOpenChange,
  returnTo,
  contentId,
}: {
  item?: LearningEvidence;
  related: (LearningEvidence | undefined)[];
  open: boolean;
  onOpenChange: (value: boolean) => void;
  returnTo: RefObject<HTMLButtonElement | undefined>;
  contentId: string;
}) {
  if (!item) return null;
  return (
    <DialogContent
      open={open}
      title={`本学习样例依据〔${item.alias}〕`}
      description="只核对当前合成学习样例内的公开摘要，不跨盘复用短别名，也不读取你的出生资料。"
      sheet
      contentId={contentId}
      onOpenChange={onOpenChange}
      onReturnFocus={() => {
        const previous = returnTo.current;
        (previous?.isConnected ? previous : document.getElementById('study-learning-heading'))?.focus({
          preventScroll: true,
        });
      }}>
      <div className="study-evidence stack">
        <EvidenceBody item={item} />
        {related.map((input, index) => (
          <section className="study-evidence-input stack small" key={input?.claim_id ?? `missing-${index}`}>
            {input ? (
              <>
                <h3>输入依据〔{input.alias}〕</h3>
                <EvidenceBody item={input} />
              </>
            ) : (
              <p>这条输入依据暂不可用，未补造说明。</p>
            )}
          </section>
        ))}
      </div>
    </DialogContent>
  );
}
