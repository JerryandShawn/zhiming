import { useState } from 'react';
import { useResource } from '../api/useResource';
import { Disclosure, Segmented } from '../components/ui/Controls';
import { BaziData, ZiweiData, AstroData } from './ChartData';
import { localDate, record, ResourceState, text } from './common';
import DateField from './DateField';
import ZiweiPalaces from '../charts/ZiweiPalaces';
import AstroDiagram from '../charts/AstroDiagram';
import TimeBasis from '../charts/TimeBasis';

const tabs = [
  { value: 'bazi', label: '八字' },
  { value: 'ziwei', label: '紫微' },
  { value: 'astro', label: '星盘' },
];
const paths: Record<string, string> = { bazi: '/api/chart', ziwei: '/api/chart_ziwei', astro: '/api/chart_astro' };
export default function Chart() {
  const params = new URLSearchParams(location.hash.split('?')[1]);
  const initial = params.get('tab') ?? 'bazi';
  const [tab, setTab] = useState(Object.hasOwn(paths, initial) ? initial : 'bazi');
  const [date, setDate] = useState(params.get('date') ?? localDate());
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(date);
  const query = useResource<Record<string, unknown>>(
    validDate ? `${paths[tab]}?date=${encodeURIComponent(date)}` : null,
  );
  function select(nextTab: string, nextDate: string) {
    setTab(nextTab);
    setDate(nextDate);
    if (/^\d{4}-\d{2}-\d{2}$/.test(nextDate)) history.replaceState(null, '', `#/chart?tab=${nextTab}&date=${nextDate}`);
  }
  const data = query.data,
    meta = record(data?.core_meta),
    method = record(data?.method),
    quality = record(data?.quality);
  const branches = Array.isArray(meta.branches) ? meta.branches.length : Object.keys(record(meta.branches)).length;
  return (
    <div className="page" data-page="chart">
      <header className="page-heading desktop-heading">
        <h1>命盘</h1>
      </header>
      <div className="stack">
        <Segmented label="命盘体系" options={tabs} value={tab} onChange={(value) => select(value, date)} />
        <DateField label="查看日期" value={date} onChange={(value) => select(tab, value)} />
      </div>
      {!validDate ? (
        <p role="alert">请填写 YYYY-MM-DD 日期。</p>
      ) : (
        <ResourceState
          loading={query.isPending}
          error={query.error}
          retry={() => {
            void query.refetch();
          }}
        />
      )}
      {query.error && (
        <p>
          排盘需要已核对的资料。
          <a className="text-link quiet-link" href="#/me?section=profile">
            核对出生资料
          </a>
        </p>
      )}
      {data && validDate && (
        <>
          {branches > 1 && (
            <p className="small-text">存在 {branches} 个出生时刻候选；下面展示首个候选盘，不能当作确定时刻。</p>
          )}
          {tab === 'bazi' ? (
            <BaziData data={data} />
          ) : tab === 'ziwei' ? (
            <>
              <ZiweiPalaces data={data} date={date} />
              <ZiweiData data={data} />
            </>
          ) : (
            <>
              <AstroDiagram data={data} />
              <AstroData data={data} />
            </>
          )}
          <TimeBasis data={data} />
          <section className="section">
            <Disclosure title="计算口径与限制">
              <p className="meta">盘面来自本次程序计算。出生资料原值仅在资料确认页展示。</p>
              {['zodiac', 'houses', 'ephemeris', 'day_sect', 'dayun_sect', 'time_scale', 'xiyongshen']
                .filter((key) => method[key] !== undefined)
                .map((key) => (
                  <p key={key}>
                    {key}：{text(method[key]) || '详见计算说明'}
                  </p>
                ))}
              {Array.isArray(quality.limitations) &&
                quality.limitations
                  .filter((item): item is string => typeof item === 'string')
                  .map((item) => <p key={item}>{item}</p>)}
              {Array.isArray(meta.warnings) &&
                meta.warnings
                  .filter((item): item is string => typeof item === 'string')
                  .map((item) => <p key={item}>{item}</p>)}
            </Disclosure>
          </section>
        </>
      )}
    </div>
  );
}
