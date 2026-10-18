import { Disclosure } from '../components/ui/Controls';
import { label, list, longitude, object, positionLabel, signs, wheelPoint, type ChartRecord } from './data';
import './charts.css';

const shortNames: Record<string, string> = {
  太阳: '日',
  月亮: '月',
  水星: '水',
  金星: '金',
  火星: '火',
  木星: '木',
  土星: '土',
  天王: '天',
  天王星: '天',
  海王: '海',
  海王星: '海',
  冥王: '冥',
  冥王星: '冥',
};
const kinds: Record<string, string> = {
  合相: 'conjunction',
  六合: 'harmonious',
  拱相: 'harmonious',
  刑相: 'tense',
  冲相: 'tense',
};
export default function AstroDiagram({ data }: { data: ChartRecord }) {
  const planets = Object.entries(object(data.planets)).flatMap(([name, value]) => {
    const row = object(value),
      angle = longitude(row.longitude);
    return angle === null ? [] : [{ name, angle, row }];
  });
  const byName = new Map(planets.map((planet) => [planet.name, planet]));
  const houses = list(data.houses).flatMap((row) => {
    const angle = longitude(row.longitude);
    return angle === null ? [] : [{ angle, house: label(row.house) }];
  });
  const ascendant = longitude(object(data.asc).longitude);
  const origin = ascendant ?? 0;
  const aspects = list(data.aspects);
  const visibleAspects = aspects.filter(
    (row) => byName.has(label(row.from)) && byName.has(label(row.to)) && kinds[label(row.aspect)],
  );
  return (
    <section className="section chart-astro" aria-label="星盘角度可视化">
      <h2>本命星盘轮</h2>
      {planets.length ? (
        <>
          <svg
            className="chart-astro-wheel"
            viewBox="0 0 400 400"
            role="img"
            aria-label={`本命星盘轮，${planets.length}颗星体，${visibleAspects.length}条已返回相位`}>
            <title>按已返回黄经绘制；{ascendant === null ? '未返回上升，白羊零度朝左' : '上升朝左'}。</title>
            {[190, 163, 112].map((radius) => (
              <circle key={radius} cx="200" cy="200" r={radius} className="chart-wheel-ring" />
            ))}
            {signs.map((sign, index) => {
              const start = wheelPoint(index * 30, 163, origin),
                end = wheelPoint(index * 30, 190, origin);
              const text = wheelPoint(index * 30 + 15, 177, origin);
              return (
                <g key={sign}>
                  <line x1={start.x} y1={start.y} x2={end.x} y2={end.y} className="chart-wheel-ring" />
                  <text
                    x={text.x}
                    y={text.y}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    className="chart-zodiac-label">
                    {sign}
                  </text>
                </g>
              );
            })}
            {houses.map((house, index) => {
              const start = wheelPoint(house.angle, 112, origin),
                end = wheelPoint(house.angle, 163, origin);
              return (
                <line
                  key={index}
                  x1={start.x}
                  y1={start.y}
                  x2={end.x}
                  y2={end.y}
                  className="chart-house-line"
                  data-house={house.house}>
                  <title>
                    第{house.house}宫头 {positionLabel(house.angle)}
                  </title>
                </line>
              );
            })}
            {visibleAspects.map((aspect, index) => {
              const from = wheelPoint(byName.get(label(aspect.from))!.angle, 112, origin);
              const to = wheelPoint(byName.get(label(aspect.to))!.angle, 112, origin);
              return (
                <line
                  key={index}
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  className={`chart-aspect ${kinds[label(aspect.aspect)]}`}
                  data-aspect={`${label(aspect.from)}-${label(aspect.to)}`}>
                  <title>
                    {label(aspect.from)}
                    {label(aspect.aspect)}
                    {label(aspect.to)}，容许度{label(aspect.orb)}°
                  </title>
                </line>
              );
            })}
            {planets.map((planet, index) => {
              const anchor = wheelPoint(planet.angle, 112, origin),
                point = wheelPoint(planet.angle, 127 + (index % 3) * 13, origin);
              return (
                <g key={planet.name} data-planet={planet.name} data-longitude={planet.angle}>
                  <line x1={anchor.x} y1={anchor.y} x2={point.x} y2={point.y} className="chart-planet-leader" />
                  <circle cx={anchor.x} cy={anchor.y} r="2" className="chart-planet-dot" />
                  <text x={point.x} y={point.y} textAnchor="middle" dominantBaseline="middle">
                    <title>
                      {planet.name} {positionLabel(planet.angle)}
                    </title>
                    {shortNames[planet.name] || planet.name.slice(0, 1)}
                  </text>
                </g>
              );
            })}
          </svg>
          <p className="meta">金色：合相 · 玉色：和谐 · 朱砂：张力。相位含义同时在下表保留，不只靠颜色辨认。</p>
          {ascendant === null && (
            <p className="small-text">未返回上升角度，轮图以白羊零度朝左；不能据此认定上升宫位。</p>
          )}
          {(houses.length !== 12 || new Set(houses.map((house) => house.house)).size !== 12) && (
            <p className="small-text">宫头数据不完整，只绘制已返回的宫位线，不补画等分宫位。</p>
          )}
        </>
      ) : (
        <p>没有可用的星体黄经，暂不能绘制星盘轮。</p>
      )}
      <Disclosure title="核对轮图角度与相位">
        {planets.map((planet) => (
          <p key={planet.name}>
            {planet.name}：{positionLabel(planet.angle)} · 黄经 {planet.angle.toFixed(2)}°
            {planet.row.retrograde === true ? ' · 逆行' : ''}
          </p>
        ))}
        {aspects.map((aspect, index) => (
          <p key={index}>
            {label(aspect.from)} {label(aspect.aspect)} {label(aspect.to)} · 容许度 {label(aspect.orb)}°
          </p>
        ))}
        {!aspects.length && <p>未返回相位列表，不能自行补线。</p>}
        {visibleAspects.length < aspects.length && <p>部分相位缺少端点或类型，只保留文字，不补画连线。</p>}
      </Disclosure>
    </section>
  );
}
