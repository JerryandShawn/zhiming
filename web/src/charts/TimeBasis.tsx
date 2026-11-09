import { Tag } from '../components/ui/Controls';
import { label, list, object, type ChartRecord } from './data';
import './charts.css';

const pillarNames = { year: '年柱', month: '月柱', day: '日柱', hour: '时柱' };
const differences: Record<string, string> = {
  'bazi.pillars.year': '年柱不同',
  'bazi.pillars.month': '月柱不同',
  'bazi.pillars.day': '日柱不同',
  'bazi.pillars.hour': '时柱不同',
  'ziwei.palaces': '十二宫配置不同',
  'ziwei.ming_gong': '命宫不同',
  'ziwei.shen_gong': '身宫不同',
  'ziwei.lunar_date': '农历换算不同（原日期仅在资料确认页核对）',
  'ziwei.wuxing_ju': '五行局不同',
};
const identifier = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0;
function ChartSummary({ chart }: { chart: ChartRecord }) {
  const pillars = object(object(chart.data).pillars);
  const ziwei = object(chart.ziwei_column);
  return (
    <div className="stack small">
      <p>
        {Object.entries(pillarNames)
          .map(([key, name]) => `${name} ${label(object(pillars[key]).ganzhi) || label(pillars[key]) || '未提供'}`)
          .join(' · ')}
      </p>
      <p className="small-text">
        紫微命宫 {label(ziwei.ming_gong) || '未提供'} · 身宫 {label(ziwei.shen_gong) || '未提供'}
      </p>
      {label(ziwei.wuxing_ju) && <p className="small-text">五行局：{label(ziwei.wuxing_ju)}</p>}
    </div>
  );
}
export default function TimeBasis({ data }: { data: ChartRecord }) {
  const basis = object(data.time_basis);
  const readout = object(data.interpretation ?? data.readout ?? basis.readout);
  const charts = list(data.charts);
  const ids = Array.isArray(readout.primary_chart_ids) ? readout.primary_chart_ids : null;
  const primary = charts.filter(
    (chart) => object(chart.time_basis).basis === 'true_solar' && (!ids || ids.includes(chart.id)),
  );
  const comparisons = list(readout.comparisons);
  const confirmation = readout.physical_instant_confirmation_required === true || basis.requires_confirmation === true;
  return (
    <section className="section chart-time-basis" aria-label="时辰口径核对">
      <h2>时辰口径</h2>
      {!primary.length ? (
        <>
          <p>真太阳时为默认解读口径；当前响应尚未提供可核对的真太阳时盘与北京时间差异，暂不能并列显示。</p>
          {typeof data.time_basis === 'string' && <p className="small-text">本次返回的计算说明：{data.time_basis}</p>}
          {object(data.method).equation_of_time_applied === false && (
            <p className="small-text">本次未应用均时差，不能把地方平太阳时当作完整真太阳时。</p>
          )}
        </>
      ) : (
        <>
          <p>
            <Tag>默认 · 真太阳时</Tag> 北京时间结果不同时并列；当地标准时只供计算核对。
          </p>
          {primary.map((chart, index) => {
            const comparison = comparisons.find((item) => item.primary_chart_id === chart.id);
            const other =
              comparison &&
              identifier(comparison.comparison_chart_id) &&
              identifier(object(chart.time_basis).instant_id) &&
              charts.find(
                (item) =>
                  item.id === comparison.comparison_chart_id &&
                  object(item.time_basis).basis === 'beijing_standard' &&
                  identifier(object(item.time_basis).instant_id) &&
                  object(item.time_basis).instant_id === object(chart.time_basis).instant_id,
              );
            const changed = Array.isArray(comparison?.fields_changed) && comparison.fields_changed.length > 0;
            const changedFields = Array.isArray(comparison?.fields_changed) ? comparison.fields_changed : [];
            const publicDifferences = changedFields.filter(
              (field): field is string => typeof field === 'string' && Object.hasOwn(differences, field),
            );
            const unsupported = publicDifferences.length < changedFields.length;
            return (
              <div className="chart-basis-pair" key={label(chart.id) || index}>
                <div>
                  <h3>真太阳时{primary.length > 1 ? ` · 候选 ${index + 1}` : ''}</h3>
                  <ChartSummary chart={chart} />
                </div>
                {other && changed && (
                  <div className="chart-basis-comparison">
                    <h3>按北京时间则为</h3>
                    <ChartSummary chart={other} />
                    {publicDifferences.length > 0 && (
                      <p className="small-text">
                        本次差异：{publicDifferences.map((field) => differences[field]).join('；')}。
                      </p>
                    )}
                    {unsupported && <p className="small-text">部分差异当前页暂不支持展示，需进一步核对计算说明。</p>}
                    <p className="meta">此处只显示本次核对明确报告的盘面差异。</p>
                  </div>
                )}
              </div>
            );
          })}
          {!comparisons.length && <p className="small-text">本次核对未报告需要并列的北京时间差异。</p>}
        </>
      )}
      {confirmation && (
        <p className="small-text" role="status">
          出生记录仍有重复或不存在时刻需要确认；默认口径不会替你选定一个真实时刻，也不会改写资料。
        </p>
      )}
      <p className="meta">星盘使用实际天文时刻，不把真太阳时当作新的真实时刻再做一次转换。</p>
    </section>
  );
}
