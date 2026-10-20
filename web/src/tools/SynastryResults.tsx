import { Disclosure } from '../components/ui/Controls';
import { EvidenceCatalog } from './EvidenceButton';
import type { Side, SynastryData, SynastrySample, ToolPort } from './types';
const pillarNames = { year: '年柱', month: '月柱', day: '日柱', hour: '时柱' } as const;
function SideChart({ side, data }: { side: Side; data: SynastryData }) {
  const pillars = side === 'a' ? data.bazi.pillars_a : data.bazi.pillars_b;
  const positions = side === 'a' ? data.astro.positions_a : data.astro.positions_b;
  const basis = data.basis[side];
  return (
    <section className="tool-side stack" aria-label={`${side.toUpperCase()}方盘面`}>
      <h3>{side === 'a' ? 'A 方 · 阿远（合成）' : 'B 方 · 小禾（合成）'}</h3>
      <dl className="tool-pillars">
        {Object.entries(pillars).map(([name, value]) => (
          <div key={name}>
            <dt>{pillarNames[name as keyof typeof pillarNames]}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="meta">
        八字与紫微默认真太阳时；
        {basis.comparisons.some((item) => item.has_reported_difference)
          ? '本样例报告了标准时间比较差异，但此公开投影未提供另一套盘面，暂不补画。'
          : '未报告标准时间盘面差异。'}
      </p>
      <div className="tool-table-scroll" tabIndex={0} role="region" aria-label={`${side.toUpperCase()}方星体位置`}>
        <table className="tool-table">
          <caption>{side.toUpperCase()} 方出生星体黄经 · 实际 UTC 口径</caption>
          <thead>
            <tr>
              <th scope="col">星体</th>
              <th scope="col">黄经</th>
              <th scope="col">方向</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(positions).map(([name, position]) => (
              <tr key={name}>
                <th scope="row">{name}</th>
                <td>
                  <data value={String(position.longitude)}>{position.longitude.toFixed(6)}°</data>
                </td>
                <td>{position.retrograde ? '逆行' : '顺行'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
export default function SynastryResults({ sample, port }: { sample: SynastrySample; port: ToolPort }) {
  const { data } = sample,
    combine = data.bazi.day_stem_combination;
  return (
    <div className="stack tool-results" data-tool-document={sample.document_id}>
      <section className="section stack">
        <h2>两侧盘面各自保留</h2>
        <p>这是两份固定合成盘面，不合成为一张虚构盘，也不提供匹配总分。</p>
        <div className="tool-two-sides">
          <SideChart side="a" data={data} />
          <SideChart side="b" data={data} />
        </div>
      </section>
      <section className="section stack">
        <h2>跨盘相位</h2>
        <p className="meta">
          A 方对 B 方 · 统一容许度上限 {data.astro.orb_degrees}° · 出生实际 UTC，不套真太阳时，也没有混入当天行运。
        </p>
        <div className="tool-table-scroll" tabIndex={0} role="region" aria-label="跨盘相位完整列表">
          <table className="tool-table">
            <caption>保留实际配对方向、目标相位角与实际误差</caption>
            <thead>
              <tr>
                <th scope="col">A 方星体</th>
                <th scope="col">B 方星体</th>
                <th scope="col">相位</th>
                <th scope="col">目标角</th>
                <th scope="col">实际夹角</th>
                <th scope="col">误差</th>
              </tr>
            </thead>
            <tbody>
              {data.astro.aspects.map((row) => {
                const delta = Math.abs(
                  data.astro.positions_a[row.from].longitude - data.astro.positions_b[row.to].longitude,
                );
                return (
                  <tr key={`${row.from}:${row.to}`} data-cross-aspect={`${row.from}:${row.to}`}>
                    <th scope="row">{row.from}</th>
                    <td>{row.to}</td>
                    <td>{row.aspect}</td>
                    <td>{row.angle}°</td>
                    <td>{Math.min(delta, 360 - delta).toFixed(6)}°</td>
                    <td>
                      <data value={String(row.orb_degrees)}>{row.orb_degrees.toFixed(6)}°</data>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!data.astro.aspects.length && <p>这个样例在当前统一容许度内没有返回跨盘相位，不补画或补算。</p>}
      </section>
      <section className="section stack">
        <h2>八字结构对读</h2>
        <p>
          两侧日干 {combine.a}、{combine.b}：{combine.met ? '有五合结构' : '未返回五合结构'}；不据此宣布合化。
        </p>
        <Disclosure title={`已返回的跨盘六合与六冲（${data.bazi.branch_relations.length}组）`}>
          {data.bazi.branch_relations.map((row, index) => (
            <p key={index}>
              A 方{pillarNames[row.a_pillar]} {row.a} ↔ B 方{pillarNames[row.b_pillar]} {row.b} · {row.kind}
            </p>
          ))}
          {!data.bazi.branch_relations.length && <p>没有返回这两类跨盘配对，不等于没有其他相处条件。</p>}
        </Disclosure>
        <Disclosure title="表层元素与三种候选路径">
          <p>
            只比较表层出现项，不评估气量与旺衰。候选干取并集，不代表方法共识或唯一喜用；不能说一个人需要被另一个人“补足”。
          </p>
          {data.bazi.element_complement.map((row) => (
            <p key={row.recipient}>
              {row.recipient.toUpperCase()} 方未出现、对方出现的表层元素：{row.elements.join('、') || '无'}
            </p>
          ))}
          <ul>
            {data.bazi.useful_complement.map((row) => (
              <li key={`${row.recipient}:${row.method}`}>
                {row.recipient.toUpperCase()} 方 · {row.method}候选 {row.candidate_stems.join('、') || '无'}；对方透干{' '}
                {row.other_exposed_stems.join('、') || '无'}；交集 {row.overlap.join('、') || '无'}。未判断有效力量。
              </li>
            ))}
          </ul>
        </Disclosure>
      </section>
      <section className="section stack">
        <h2>紫微两侧对读</h2>
        <p className="meta">仅有已返回的夫妻宫与对方命宫；这不是两份完整十二宫盘，也不产生适配分数。</p>
        {data.ziwei.cross_views.map((row) => (
          <article className="tool-candidate" key={row.recipient}>
            <h3>{row.recipient.toUpperCase()} 方夫妻宫 ↔ 对方命宫</h3>
            <p>
              自己的夫妻宫 {row.own_spouse_palace.ganzhi}：
              {[...row.own_spouse_palace.major, ...row.own_spouse_palace.minor].join('、') || '未返回星名'}
            </p>
            <p>
              对方命宫 {row.other_life_palace.ganzhi}：
              {[...row.other_life_palace.major, ...row.other_life_palace.minor].join('、') || '未返回星名'}
            </p>
            <p className="meta">
              {row.same_branch ? '宫支相同' : '宫支不同'}；共有星名 {row.shared_star_names.join('、') || '无'}
              。只说明结构，不判断关系结局。
            </p>
          </article>
        ))}
      </section>
      <EvidenceCatalog sample={sample} port={port} />
      <Disclosure title="本次展示的范围与限制">
        {sample.limits.map((limit) => (
          <p key={limit}>{limit}</p>
        ))}
        <p>不会评价人品、忠诚，也不预告分手或婚育；盘面不替代双方意愿。</p>
      </Disclosure>
    </div>
  );
}
