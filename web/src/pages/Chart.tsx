import { useState } from 'react';
import { AstroWheel, ElementBar, LuckTimeline, PalaceGrid, PillarColumn, StrengthCompare } from '../components/Charts';
import { Disclosure, Segmented } from '../components/ui/Controls';
import { DatePicker } from '../components/DatePicker';

const tabs = [
  { value: 'bazi', label: '八字' },
  { value: 'ziwei', label: '紫微' },
  { value: 'astro', label: '星盘' },
] as const;
export default function Chart() {
  const parameter = new URLSearchParams(location.hash.split('?')[1]).get('tab');
  const [tab, setTab] = useState<'bazi' | 'ziwei' | 'astro'>(
    parameter === 'ziwei' || parameter === 'astro' ? parameter : 'bazi',
  );
  const [scale, setScale] = useState('本命');
  return (
    <div className="page" data-page="chart">
      <header className="page-heading desktop-heading">
        <h1>命盘</h1>
      </header>
      <div className="stack">
        <Segmented label="命盘体系" options={tabs} value={tab} onChange={setTab} />
        <div className="row between wrap">
          <DatePicker />
          <span className="meta" title="已确认的合成资料">
            阿远
          </span>
        </div>
        <Segmented
          label="时间尺度"
          options={['本命', '流年', '流月', '流日'].map((value) => ({ value, label: value }))}
          value={scale}
          onChange={setScale}
        />
      </div>
      {tab === 'bazi' ? (
        <div className="page-grid">
          <div>
            <PillarColumn />
            <ElementBar />
            <StrengthCompare />
          </div>
          <aside>
            <section className="section">
              <h2>格局与喜用</h2>
              <p>偏印格候选 · 示例</p>
              <p className="secondary-text">先看季节与根气， 再把不同口径放在一起，不凭一个字下结论。</p>
              <Disclosure title="查看依据" count="两种思路">
                <p>合成示例，仅展示解释结构。</p>
              </Disclosure>
            </section>
            <LuckTimeline />
            <section className="section">
              <h2>流年与流月</h2>
              <p className="small-text">2026 丙午 · 寒露后 戊戌月</p>
            </section>
          </aside>
        </div>
      ) : (
        <section className="section">{tab === 'ziwei' ? <PalaceGrid /> : <AstroWheel />}</section>
      )}
      <section className="section">
        <Disclosure title="计算口径与引擎" count="真太阳时 · 节气口径 · 合成示例">
          <p className="small-text">此处只展示界面。实际计算、边界和证据将在后续接口接入时核对。</p>
        </Disclosure>
      </section>
    </div>
  );
}
