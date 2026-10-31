import { Button, Disclosure, Tag } from '../../components/ui/Controls';
import { Panel } from '../../components/ui/Overlays';
import type { DailyEvidence, DailyHighlight, DailyTransitView, TodayPort } from './types';
const systems = { bazi: '八字', ziwei: '紫微', astro: '星盘' } as const;
function resolve(port: TodayPort, transit: DailyTransitView, highlight: DailyHighlight): DailyEvidence[] {
  return highlight.refs.flatMap((ref) => {
    if (ref.date !== transit.date || ref.documentId !== transit.documentId) return [];
    try {
      const evidence = port.resolveEvidence(ref);
      return evidence &&
        evidence.ref.date === ref.date &&
        evidence.ref.documentId === ref.documentId &&
        evidence.ref.alias === ref.alias
        ? [evidence]
        : [];
    } catch {
      return [];
    }
  });
}

export default function TodayTransit({ transit, port }: { transit: DailyTransitView; port: TodayPort }) {
  return (
    <div className="today-transit stack">
      <div>
        <Tag>合成引擎样例</Tag>
        <h3>
          {transit.dayGanzhi}
          {transit.dayTenGod ? ` · ${transit.dayTenGod}` : ''}
        </h3>
      </div>
      <p className="small-text secondary-text">
        固定合成盘面，默认按真太阳时。这里的结果不是你的档案，也不是对现实结果的保证。
      </p>
      {transit.highlights.map((highlight) => {
        const evidence = resolve(port, transit, highlight);
        return (
          <article className="today-highlight" key={highlight.id} data-daily-system={highlight.system}>
            <p className="meta">
              {systems[highlight.system]} · {highlight.school}
            </p>
            <h3>{highlight.title}</h3>
            <p>{highlight.summary}</p>
            {evidence.length ? (
              <Panel
                sheet
                title={`${systems[highlight.system]}流日依据`}
                description="只展示当前日期已核对的公开依据说明。"
                trigger={<Button variant="ghost">查看{systems[highlight.system]}依据</Button>}>
                <div className="stack today-evidence">
                  {evidence.map((item) => (
                    <section key={item.ref.alias}>
                      <h3>{item.label}</h3>
                      <p>{item.summary}</p>
                      <p className="meta">
                        依据别名：{item.ref.alias} · {item.ref.date}
                      </p>
                    </section>
                  ))}
                </div>
              </Panel>
            ) : (
              <p className="meta">这条说明的依据暂未载入。</p>
            )}
          </article>
        );
      })}
      {!transit.highlights.length && <p className="meta">这一天还没有可公开展示的流日要点。</p>}
      <Disclosure title="计算口径与展示范围">
        <p>使用已发布的合成引擎样例，不重新计算，也不会替换你的资料。</p>
        <p>
          {transit.hasBeijingComparison
            ? '样例同时保留北京时间比较口径，具体差异请到命盘页逐项核对。'
            : '没有明确的北京时间盘面差异，不制造并列结论。'}
        </p>
        {transit.limits.map((limit, index) => (
          <p key={index}>{limit}</p>
        ))}
        <p className="meta">
          {transit.provenance.contractStatus === 'offset_normalized'
            ? '样例时间做过格式归一；内容及依据别名已核对，不代表原始时间格式已经通过完整契约验收。'
            : '已核对公开样例的内容与依据别名，不代表现实准确性验收。'}
        </p>
      </Disclosure>
    </div>
  );
}
