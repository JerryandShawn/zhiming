import { useId } from 'react';
import type { SynastryData } from './types';
import './elements.css';

type Visible = SynastryData['bazi']['visible_a'];
const order = ['木', '火', '土', '金', '水'];

function Count({ side, element }: { side?: Visible; element: string }) {
  const counts = side?.element_counts;
  const value = counts && Object.hasOwn(counts, element) ? counts[element] : undefined;
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value) && value >= 0 ? (
    <data value={String(value)}>{value}</data>
  ) : (
    <span className="meta">未返回可用值</span>
  );
}

/** Returned occurrence counts only: no derived totals, percentages, strength or compatibility scoring. */
export function ElementComparison({ a, b }: { a?: Visible; b?: Visible }) {
  const id = useId();
  const returned = [...new Set([...Object.keys(a?.element_counts ?? {}), ...Object.keys(b?.element_counts ?? {})])];
  const elements = [
    ...order.filter((element) => returned.includes(element)),
    ...returned.filter((element) => !order.includes(element)),
  ];
  return (
    <section className="tool-elements stack small" aria-labelledby={`${id}-title`}>
      <h3 id={`${id}-title`}>表层五行计数</h3>
      <p id={`${id}-scope`} className="small-text secondary-text">
        按本次样例返回的口径，逐项对照表层出现次数；不代表气量、旺衰、喜忌或关系适配，也不合计为总分。
      </p>
      {elements.length ? (
        <div
          className="tool-table-scroll"
          tabIndex={0}
          role="region"
          aria-label="双方表层五行计数"
          aria-describedby={`${id}-scope ${id}-missing`}>
          <table className="tool-table tool-element-table">
            <caption>已返回的表层出现次数</caption>
            <thead>
              <tr>
                <th scope="col">五行</th>
                <th scope="col">A方计数</th>
                <th scope="col">B方计数</th>
              </tr>
            </thead>
            <tbody>
              {elements.map((element) => (
                <tr key={element} data-element={element}>
                  <th scope="row">{element}</th>
                  <td data-side="a">
                    <Count side={a} element={element} />
                  </td>
                  <td data-side="b">
                    <Count side={b} element={element} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p role="status">当前没有返回可对照的五行计数，不补成全0。</p>
      )}
      <p id={`${id}-missing`} className="meta">
        0表示该侧本次计数为0；未返回的值保持未返回，不补0，也不由其他侧推算。
      </p>
    </section>
  );
}
