import { Disclosure } from '../components/ui/Controls';
import { EvidenceButton } from './EvidenceButton';
import type { ToolPort, WindowHit, WindowSample } from './types';
const signed = (value: number) => (value > 0 ? `+${value}` : String(value));
function Hits({
  title,
  items,
  documentId,
  port,
}: {
  title: string;
  items: WindowHit[];
  documentId: string;
  port: ToolPort;
}) {
  return (
    <Disclosure title={`${title}（${items.length}项）`}>
      <ul className="tool-hits">
        {items.map((hit) => (
          <li key={`${hit.ref.document_id}:${hit.ref.alias}`}>
            <div>
              <span>
                {hit.label} · {signed(hit.contribution)}
              </span>
              <p className="meta">
                {hit.base_weight} × {hit.layer_factor}
                {hit.reason === 'incomplete_relation_zero_weight' ? '；成员不完整，按零分保留' : '；项目公开权重'}
              </p>
            </div>
            <EvidenceButton reference={hit.ref} documentId={documentId} port={port} />
          </li>
        ))}
      </ul>
      {!items.length && <p className="meta">没有返回这类计分条件。</p>}
    </Disclosure>
  );
}
export default function WindowResults({ sample, port }: { sample: WindowSample; port: ToolPort }) {
  const { data, document_id: documentId } = sample,
    page = data.pagination;
  return (
    <div className="stack tool-results" data-tool-document={documentId}>
      <section className="section">
        <h2>整个区间的项目排序</h2>
        <p className="meta">
          {data.range.start_date} 至 {data.range.end_date}（含两端）· {data.range.day_count} 天 · {data.purpose}
        </p>
        <p>分数是公开权重的启发式排序，不是成功率；不提供精确吉时。</p>
        <div className="tool-table-scroll" tabIndex={0} role="region" aria-label="全区间日期排序">
          <table className="tool-table">
            <caption>按项目总分降序，同分按日期升序</caption>
            <thead>
              <tr>
                <th scope="col">排名</th>
                <th scope="col">日期</th>
                <th scope="col">总分</th>
                <th scope="col">正向合计</th>
                <th scope="col">负向合计</th>
              </tr>
            </thead>
            <tbody>
              {data.ranking_summary.map((row) => (
                <tr key={row.date}>
                  <th scope="row">{row.rank}</th>
                  <td>{row.date}</td>
                  <td>{signed(row.score)}</td>
                  <td>{signed(row.positive_sum)}</td>
                  <td>{signed(row.negative_sum)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="section stack">
        <h2>当前查看的日期</h2>
        <p className="meta">
          区间共 {page.total} 天 · 当前返回 {page.returned} 天
          {data.candidates.length > 0 &&
            ` · 第 ${data.candidates[0].rank}${data.candidates.length > 1 ? `–${data.candidates.at(-1)!.rank}` : ''} 名`}
        </p>
        {!data.candidates.length && (
          <div role="status">
            <p>这已是末尾空页。</p>
            <p className="meta">当前页没有候选，不表示整个区间没有条件；完整排序仍在上方。</p>
          </div>
        )}
        {data.candidates.map((row) => (
          <article className="tool-candidate stack small" key={row.date}>
            <h3>
              第 {row.rank} 位 · {row.date}
            </h3>
            <p>项目总分 {signed(row.score)}</p>
            <Hits title="正向条件" items={row.positive_hits} documentId={documentId} port={port} />
            <Hits title="负向条件" items={row.negative_hits} documentId={documentId} port={port} />
            <Hits title="保留而不计方向分" items={row.neutral_hits} documentId={documentId} port={port} />
          </article>
        ))}
      </section>
      <Disclosure title="计算依据与限制">
        <p>北京时间 12:00 快照；西占当日相位容许度 {data.method.daily_orb_degrees}°，没有搜索全天时辰。</p>
        <p>
          层因子：流年 {data.weights.layer_factors.yearly}、流月 {data.weights.layer_factors.monthly}、流日{' '}
          {data.weights.layer_factors.daily}。正负分只是本项目的公开排序约定。
        </p>
        <p className="meta">
          分页核对：偏移 {page.offset} · 本页上限 {page.limit} · {page.has_more ? '还有后续明细' : '已到末尾'}。
        </p>
        <p>未采用条件 {data.ignored_condition_count} 项；不会补造成已命中。</p>
        {sample.limits.map((limit) => (
          <p key={limit}>{limit}</p>
        ))}
      </Disclosure>
    </div>
  );
}
