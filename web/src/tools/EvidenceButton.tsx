import { Button, Disclosure } from '../components/ui/Controls';
import { DeferredPanel } from '../components/ui/DeferredPanel';
import type { EvidenceRef, PublicEvidence, PublishedSample, ToolPort } from './types';
const same = (a: EvidenceRef, b: EvidenceRef) => a.document_id === b.document_id && a.alias === b.alias;
const officialLinks = new Set([
  'https://www.astro.com/swisseph/swephprg.htm',
  'https://docs.iztro.com/posts/astrolabe',
]);
export function EvidenceSource({ item }: { item: PublicEvidence }) {
  if (item.kind !== 'rule') return null;
  if (!item.school_label || !item.source)
    return <p className="meta">流派与出处尚未接入公开说明；不以文件版本代替术数出处。</p>;
  const link = item.source.url && officialLinks.has(item.source.url) ? item.source.url : undefined;
  return (
    <div className="stack small">
      <p>流派与方法：{item.school_label}</p>
      <p>
        出处：
        {link ? (
          <a href={link} target="_blank" rel="noopener noreferrer">
            {item.source.title}
          </a>
        ) : (
          item.source.title
        )}
      </p>
      {item.source.status && <p className="meta">适用范围：{item.source.status}</p>}
    </div>
  );
}
export function EvidenceButton({
  reference,
  documentId,
  port,
}: {
  reference: EvidenceRef;
  documentId: string;
  port: ToolPort;
}) {
  let item: PublicEvidence | undefined;
  try {
    if (reference.document_id === documentId) item = port.resolveEvidence(reference);
  } catch {
    /* Safe unavailable state. */
  }
  if (!item || !same(item.ref, reference)) return <span className="meta">依据暂不可用</span>;
  const linked = (item.evidence_refs ?? []).flatMap((ref) => {
    if (ref.document_id !== documentId) return [];
    try {
      const value = port.resolveEvidence(ref);
      return value && same(value.ref, ref) ? [value] : [];
    } catch {
      return [];
    }
  });
  return (
    <DeferredPanel
      title={`本结果依据〔${item.ref.alias}〕`}
      description="仅核对当前结果内的公开说明，不跨结果复用短别名。"
      sheet
      renderTrigger={(props) => (
        <Button {...props} variant="ghost">
          依据〔{item.ref.alias}〕
        </Button>
      )}>
      <div className="stack tool-evidence">
        <p>{item.summary}</p>
        <EvidenceSource item={item} />
        {linked.map((value) => (
          <section key={value.ref.alias}>
            <h3>依据〔{value.ref.alias}〕</h3>
            <p>{value.summary}</p>
            <EvidenceSource item={value} />
          </section>
        ))}
      </div>
    </DeferredPanel>
  );
}
export function EvidenceCatalog({ sample, port }: { sample: PublishedSample; port: ToolPort }) {
  return (
    <Disclosure title="本结果的公开依据">
      <div className="stack">
        {sample.evidence.map((item) => (
          <article className="tool-evidence-row" key={`${item.ref.document_id}:${item.ref.alias}`}>
            <p>{item.summary}</p>
            <EvidenceButton reference={item.ref} documentId={sample.document_id} port={port} />
          </article>
        ))}
        {!sample.evidence.length && <p>当前页没有规则依据；这不表示整个区间没有条件。</p>}
      </div>
    </Disclosure>
  );
}
