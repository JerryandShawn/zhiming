import { Tag } from '../components/ui/Controls';
import { ChartBasis } from './ChartBasis';
import { label, list, object, type ChartRecord } from './data';
import './charts.css';

function validDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value;
}
function timestamp(value: unknown) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value))
    return null;
  if (!validDate(value.slice(0, 10))) return null;
  if (Number(value.slice(11, 13)) > 23 || Number(value.slice(14, 16)) > 59 || Number(value.slice(17, 19)) > 59)
    return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}
export default function LuckPeriods({ data, date }: { data: ChartRecord; date: string }) {
  const extended = object(object(data.p8).decade_luck);
  const hasExtended = list(extended.decades).length > 0;
  const periods = hasExtended ? list(extended.decades) : list(data.dayun);
  const year = validDate(date) ? Number(date.slice(0, 4)) : null;
  const snapshot = object(object(object(data.p8).calendar_layers).day);
  const explicit = Object.hasOwn(snapshot, 'sample_at') || Object.hasOwn(data, 'sample_at');
  const sample = explicit
    ? timestamp(Object.hasOwn(snapshot, 'sample_at') ? snapshot.sample_at : data.sample_at)
    : year !== null
      ? timestamp(`${date}T12:00:00+08:00`)
      : null;
  return (
    <section className="section chart-luck">
      <h2>大运 · 逐步查看</h2>
      {hasExtended && (
        <p className="meta">
          {explicit ? '按本次返回的快照核对交运边界。' : '按所选日期北京时间正午快照核对交运边界，不表示此刻正在交运。'}
        </p>
      )}
      {hasExtended && sample === null && <p className="small-text">快照时间无效，暂不标出所属大运。</p>}
      {!hasExtended && periods.length > 0 && (
        <p className="meta">只有按年份划分的大运字段；高亮仅为所选年份示意，不是精确交运时刻。</p>
      )}
      <div className="chart-luck-scroll" role="region" aria-label="可点开解释的大运时间线，可左右滚动" tabIndex={0}>
        {periods.map((period, index) => {
          const start = label(period.start_year ?? period.legacy_start_year);
          const end = label(period.end_year ?? period.legacy_end_year);
          const age = label(period.start_age ?? period.legacy_start_age);
          const startAt = timestamp(period.nominal_start_at),
            endAt = timestamp(period.nominal_end_exclusive);
          const validBounds = startAt !== null && endAt !== null && startAt < endAt;
          const current = hasExtended
            ? sample !== null && validBounds && startAt <= sample && sample < endAt
            : year !== null &&
              /^\d{4}$/.test(start) &&
              /^\d{4}$/.test(end) &&
              year >= Number(start) &&
              year <= Number(end);
          const path = hasExtended ? `p8.decade_luck.decades.${index}` : `dayun.${index}`;
          const ganzhi = label(period.ganzhi) || '干支未提供';
          return (
            <ChartBasis
              key={index}
              title={`${ganzhi} · 大运依据`}
              system="bazi"
              date={date}
              path={path}
              trigger={
                <button
                  type="button"
                  className={`chart-luck-period ${current ? 'current' : ''}`}
                  aria-label={`查看${ganzhi}大运解释`}
                  aria-current={current && hasExtended ? 'date' : undefined}>
                  <span className="chart-luck-status">
                    {current ? (
                      <Tag tone="accent">{hasExtended ? '快照所在' : '所选年份示意'}</Tag>
                    ) : (
                      <span className="meta">起始 {age || '未知'} 岁</span>
                    )}
                  </span>
                  <span className="meta">
                    {start || '未提供'}–{end || '未提供'}
                  </span>
                  <span className="luck-glyph">{ganzhi}</span>
                  {current && <span className="meta">起始 {age || '未知'} 岁</span>}
                  <span className="meta">
                    {label(period.ten_god) ||
                      label(period.stem_ten_god) ||
                      label(object(period.stem).ten_god) ||
                      '十神未提供'}
                  </span>
                </button>
              }>
              <p>
                这一段的盘面干支为{ganzhi}。年份范围 {start || '未提供'}–{end || '未提供'}，起始年龄 {age || '未提供'}。
              </p>
              <p>大运是传统十年分段的计算字段，不是这十年会发生什么的预测。可用它梳理阶段问题，再用现实资料核对。</p>
              {label(period.nominal_start_at) && (
                <p className="small-text">
                  程序交运边界：{label(period.nominal_start_at)} 至 {label(period.nominal_end_exclusive)}（不含终点）。
                </p>
              )}
              <p className="meta">
                {label(extended.precision) || '这里只提供按年份与起始年龄显示的分段，未提供精确交运时刻。'}
              </p>
              {hasExtended && !validBounds && <p className="small-text">这段交运边界未能核对，暂不标作所属大运。</p>}
            </ChartBasis>
          );
        })}
      </div>
      {!periods.length && <p>没有返回大运分段，暂不能展开解释。</p>}
    </section>
  );
}
