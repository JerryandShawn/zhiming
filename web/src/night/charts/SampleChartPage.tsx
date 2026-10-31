import { useEffect, useState } from 'react';
import { Disclosure, Segmented } from '../../components/ui/Controls';
import { BaziData } from '../../live/ChartData';
import { localDate } from '../../live/common';
import ZiweiPalaces from '../../charts/ZiweiPalaces';
import AstroDiagram from '../../charts/AstroDiagram';
import TimeBasis from '../../charts/TimeBasis';
import { object } from '../../charts/data';
import { chartSamples } from './port';
import './samples.css';

type ChartSystem = 'bazi' | 'ziwei' | 'astro';
function readSystem(): ChartSystem {
  const value = new URLSearchParams(location.hash.split('?')[1]).get('tab');
  return value === 'ziwei' || value === 'astro' ? value : 'bazi';
}
export default function SampleChartPage() {
  const [system, setSystem] = useState<ChartSystem>(readSystem);
  useEffect(() => {
    const update = () => setSystem(readSystem());
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  function chooseSystem(value: ChartSystem) {
    setSystem(value);
    const url = new URL(location.href),
      query = new URLSearchParams(location.hash.split('?')[1]);
    query.set('tab', value);
    url.hash = `/chart?${query.toString()}`;
    history.replaceState(history.state, '', url);
  }
  const date = localDate(),
    sample = chartSamples[system];
  return (
    <div
      className="page night-chart-samples"
      data-page="chart"
      data-runtime="night-chart-samples"
      data-chart-system={system}
      data-source-sha256={sample.sourceSha256}>
      <header className="page-heading">
        <h1>阿远 · 合成画像计算样例</h1>
        <p className="secondary-text">固定离线结果，不是你的档案。这里只核对已返回的盘面结构，不推断你的人生。</p>
        <p className="meta">时间轴核对日期：{date}。盘面与流日是固定离线快照，不会重新计算。</p>
      </header>
      <Segmented<ChartSystem>
        label="命盘体系"
        value={system}
        onChange={chooseSystem}
        options={[
          { value: 'bazi', label: '八字' },
          { value: 'ziwei', label: '紫微' },
          { value: 'astro', label: '星盘' },
        ]}
      />
      {system === 'bazi' && (
        <p className="meta">当前预览只展示安全的年龄与年份，精确交运时分暂不展示，也不据此标记精确所属运段。</p>
      )}
      {system === 'bazi' ? (
        <BaziData
          data={{ ...sample.data, day_master: sample.data.day_master ?? object(object(sample.data.pillars).day).gan }}
        />
      ) : system === 'ziwei' ? (
        <ZiweiPalaces data={sample.data} date={date} />
      ) : (
        <AstroDiagram data={sample.data} />
      )}
      <TimeBasis data={sample.basis} />
      <section className="section stack small" aria-label="本页展示范围">
        <h2>本页展示范围</h2>
        <p>按体系展示已返回的四柱与大运、紫微宫位、星盘和时辰口径。未展示的能力仍需另行核对。</p>
        <p className="meta">出生资料原值不会在此页展示。真太阳时与北京时间没有明确盘面差异时，不制造并列差异。</p>
        <Disclosure title="计算口径与样例来源">
          <p>来自已经生成的合成计算样例，三种体系各用自己的实际返回字段。</p>
          <p>这里不连接模型、不重新排盘，也不会替换你的资料；可点击盘面中的依据逐项核对。</p>
        </Disclosure>
      </section>
    </div>
  );
}
