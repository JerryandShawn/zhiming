import { useEffect, useState } from 'react';
import { CircleAlert } from 'lucide-react';
import { Button, Disclosure, Tag } from '../components/ui/Controls';
import { ChartBasis } from './ChartBasis';
import { label, list, palacePositions, type ChartRecord } from './data';
import './charts.css';

function Stars({ values }: { values: unknown }) {
  return (
    <div className="chart-stars">
      {list(values).map((star, index) => (
        <span key={index}>
          {label(star.name)} {label(star.brightness)}
          {label(star.mutagen) && (
            <span className={`chart-mutagen mutagen-${label(star.mutagen).replace('化', '')}`}>
              {label(star.mutagen).includes('忌') && <CircleAlert className="icon small" aria-hidden="true" />}化
              {label(star.mutagen).replace('化', '')}
            </span>
          )}
        </span>
      ))}
    </div>
  );
}
function PalaceExplanation({ palace }: { palace: ChartRecord }) {
  return (
    <>
      <p>
        {label(palace.name)} · {label(palace.ganzhi)}
        {palace.is_body === true ? ' · 身宫' : ''}
      </p>
      <h3>主星</h3>
      <Stars values={palace.major} />
      {!list(palace.major).length && <p>无主星；空宫也需要连同三合与对宫阅读。</p>}
      <h3>辅星</h3>
      <Stars values={palace.minor} />
      <p>
        {list(palace.linked_palaces)
          .map((row) => `${label(row.relation)}：${label(row.name)} ${label(row.ganzhi)}`)
          .join('；') || '未返回联动宫位，不能补写。'}
      </p>
      <p className="small-text">宫位和星曜只是传统结构，不代表事件必然发生；不能单看一颗星。</p>
    </>
  );
}
export default function ZiweiPalaces({ data, date }: { data: ChartRecord; date: string }) {
  const [desktop, setDesktop] = useState(() => window.matchMedia('(min-width: 1024px)').matches);
  const [manual, setManual] = useState<boolean | null>(null);
  useEffect(() => {
    const media = window.matchMedia('(min-width: 1024px)');
    const update = () => setDesktop(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  const palaces = list(data.palaces);
  const branches = palaces.map((palace) => label(palace.ganzhi).slice(-1));
  const complete =
    palaces.length === 12 && new Set(branches).size === 12 && branches.every((branch) => palacePositions[branch]);
  const grid = complete && (manual ?? desktop);
  return (
    <section className="section chart-palaces" aria-label="紫微十二宫可视化">
      <div className="row between wrap">
        <h2>十二宫盘面</h2>
        <Button disabled={!complete} aria-pressed={grid} onClick={() => setManual(!grid)}>
          {grid ? '宫位列表' : '网格'}
        </Button>
      </div>
      {!complete && <p className="small-text">宫位或地支数据不完整，先按已返回的宫位列表查看；不能补齐十二宫网格。</p>}
      <div
        className="chart-palace-scroll"
        role="region"
        aria-label={grid ? '十二宫网格，可左右滚动' : '十二宫列表'}
        tabIndex={grid ? 0 : undefined}>
        <div className={grid ? 'chart-palace-grid' : 'chart-palace-list'} data-palace-view={grid ? 'grid' : 'list'}>
          {palaces.map((palace, index) => {
            const branch = branches[index];
            const path = `palaces.${index}`;
            return grid ? (
              <ChartBasis
                key={index}
                title={`${label(palace.name)}宫位依据`}
                system="ziwei"
                date={date}
                path={path}
                trigger={
                  <button
                    type="button"
                    className="chart-palace-cell"
                    data-palace-branch={branch}
                    style={{ gridColumn: palacePositions[branch][0], gridRow: palacePositions[branch][1] }}
                    aria-label={`查看${label(palace.name)}宫位依据`}>
                    <span className="chart-palace-heading">
                      {label(palace.name)} <span className="meta">{label(palace.ganzhi)}</span>
                    </span>
                    <Stars values={palace.major} />
                    {!list(palace.major).length && <span className="small-text">无主星</span>}
                    <Stars values={palace.minor} />
                    {palace.is_body === true && <span className="meta">身宫</span>}
                  </button>
                }>
                <PalaceExplanation palace={palace} />
              </ChartBasis>
            ) : (
              <Disclosure
                key={index}
                title={`${label(palace.name)} · ${label(palace.ganzhi)}`}
                count={
                  list(palace.major)
                    .map((star) => label(star.name))
                    .join('、') || '无主星'
                }>
                <PalaceExplanation palace={palace} />
                <ChartBasis
                  title={`${label(palace.name)}宫位依据`}
                  system="ziwei"
                  date={date}
                  path={path}
                  trigger={
                    <Button variant="ghost" aria-label={`查看${label(palace.name)}宫位依据`}>
                      查看依据
                    </Button>
                  }>
                  <PalaceExplanation palace={palace} />
                </ChartBasis>
              </Disclosure>
            );
          })}
          {grid && (
            <div className="chart-palace-center">
              <Tag>本命盘</Tag>
              <h3>命宫 {label(data.ming_gong) || '未提供'}</h3>
              <p>身宫 {label(data.shen_gong) || '未提供'}</p>
              <p className="small-text">{label(data.wuxing_ju)}</p>
              <p className="meta">按返回地支定位，逐宫可查看依据。</p>
            </div>
          )}
        </div>
      </div>
      {!palaces.length && <p>尚未返回可展示的宫位。</p>}
    </section>
  );
}
