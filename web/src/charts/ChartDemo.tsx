import { useState } from 'react';
import { PillarColumn, ElementBar } from '../components/Charts';
import { Segmented, Tag } from '../components/ui/Controls';
import DateField from '../live/DateField';
import ZiweiPalaces from './ZiweiPalaces';
import AstroDiagram from './AstroDiagram';
import LuckPeriods from './LuckPeriods';
import TimeBasis from './TimeBasis';
import { astroDemo, baziDemo, timeBasisDemo, ziweiDemo } from './demo';

const tabs = [
  { value: 'bazi', label: '八字' },
  { value: 'ziwei', label: '紫微' },
  { value: 'astro', label: '星盘' },
];
export default function ChartDemo() {
  const params = new URLSearchParams(location.hash.split('?')[1]);
  const initial = params.get('tab') || 'bazi';
  const [tab, setTab] = useState(tabs.some((item) => item.value === initial) ? initial : 'bazi');
  const [date, setDate] = useState('2026-10-18');
  function select(value: string) {
    setTab(value);
    history.replaceState(null, '', `#/chart?tab=${value}`);
  }
  return (
    <div className="page" data-page="chart" data-chart-demo="synthetic">
      <header className="page-heading desktop-heading">
        <h1>命盘</h1>
      </header>
      <div className="stack">
        <Tag>合成盘面 · 组件演示</Tag>
        <p className="small-text">这些角度、宫位和分段为独立合成示例，不对应任何人的真实命盘。</p>
        <Segmented label="命盘体系" options={tabs} value={tab} onChange={select} />
        <DateField label="查看日期" value={date} onChange={setDate} />
      </div>
      {tab === 'ziwei' ? (
        <ZiweiPalaces data={ziweiDemo} date={date} />
      ) : tab === 'astro' ? (
        <AstroDiagram data={astroDemo} />
      ) : (
        <>
          <PillarColumn />
          <ElementBar />
          <LuckPeriods data={baziDemo} date={date} />
        </>
      )}
      <TimeBasis data={timeBasisDemo} />
    </div>
  );
}
