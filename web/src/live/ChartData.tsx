import type { ReactElement } from 'react';
import { Disclosure } from '../components/ui/Controls';
import { Panel } from '../components/ui/Overlays';
import { localDate, record, rows, text } from './common';

function Basis({ path, value, trigger }: { path: string; value: string; trigger?: ReactElement }) {
  const date = new URLSearchParams(location.hash.split('?')[1]).get('date') ?? localDate();
  const system = path.startsWith('palaces.') ? 'ziwei' : path.startsWith('planets.') ? 'astro' : 'bazi';
  const selection = new URLSearchParams({ date, system, focus: path, key: path });
  return (
    <Panel
      title="计算依据"
      description="下面的值来自本次已返回的计算字段，不是模型补写。"
      trigger={
        trigger ?? (
          <button type="button" className="text-link quiet-link" aria-label={`查看${path}依据`}>
            依据
          </button>
        )
      }>
      <p>{value || '此字段没有返回值。'}</p>
      <p className="meta">字段：{path}</p>
      <a className="button secondary" href={`#/chat?${selection.toString()}`}>
        带着这项依据问明镜
      </a>
    </Panel>
  );
}
export function BaziData({ data }: { data: Record<string, unknown> }) {
  const pillars = record(data.pillars),
    count = record(data.wuxing_count),
    day = record(data.day);
  const tones: Record<string, string> = { 木: 'wood', 火: 'fire', 土: 'earth', 金: 'metal', 水: 'water' };
  const elements = Object.keys(tones).map((name) => ({
    name,
    count: typeof count[name] === 'number' && Number.isFinite(count[name]) ? Math.max(0, Number(count[name])) : 0,
  }));
  const total = elements.reduce((sum, item) => sum + item.count, 0);
  return (
    <div className="stack">
      <section className="section">
        <h2>四柱</h2>
        <div className="pillars">
          {(
            [
              ['year', '年柱'],
              ['month', '月柱'],
              ['day', '日柱'],
              ['hour', '时柱'],
            ] as const
          ).map(([key, label]) => {
            const pillar = record(pillars[key]);
            const value = typeof pillars[key] === 'string' ? text(pillars[key]) : text(pillar.ganzhi);
            return (
              <article className={`pillar ${key === 'day' ? 'day-master' : ''}`} key={key}>
                <h3 className="meta">{label}</h3>
                <Basis
                  path={`pillars.${key}.ganzhi`}
                  value={value}
                  trigger={
                    <button type="button" className="pillar-glyphs" aria-label={`查看${label}${value}依据`}>
                      <span className={tones[text(pillar.wuxing_gan)]}>{value[0] || '—'}</span>
                      <span className={tones[text(pillar.wuxing_zhi)]}>{value[1] || '—'}</span>
                    </button>
                  }
                />
                <p className="meta">
                  {text(pillar.shishen_gan)} {text(pillar.shishen_zhi)}
                </p>
                <p className="meta secondary-text">
                  {Array.isArray(record(data.hidden_stems)[key])
                    ? (record(data.hidden_stems)[key] as unknown[])
                        .filter((item) => typeof item === 'string')
                        .join(' · ')
                    : ''}
                </p>
                <p className="meta">{text(pillar.nayin)}</p>
              </article>
            );
          })}
        </div>
        <p>日主：{text(data.day_master) || '未提供'}</p>
      </section>
      <section className="section">
        <h2>表层五行数量</h2>
        {total > 0 && (
          <svg
            className="element-bar"
            viewBox="0 0 100 1"
            preserveAspectRatio="none"
            role="img"
            aria-label={elements.map((item) => `${item.name}${item.count}`).join('、')}>
            {elements.map((item, index) => (
              <rect
                key={item.name}
                x={(elements.slice(0, index).reduce((sum, before) => sum + before.count, 0) / total) * 100}
                y="0"
                width={(item.count / total) * 100}
                height="1"
                fill={`var(--${tones[item.name]})`}
              />
            ))}
          </svg>
        )}
        <div className="row wrap">
          {['木', '火', '土', '金', '水'].map((name) => (
            <p key={name} className={tones[name]}>
              {name}：{text(count[name]) || '未提供'}
            </p>
          ))}
        </div>
        <p className="meta">数量不等于实际力量；不能单独据此判断吉凶。</p>
      </section>
      <section className="section">
        <h2>所选日期</h2>
        <p>
          {text(day.date)} · {text(day.day_ganzhi) || '暂无流日字段'}
        </p>
        <p className="small-text">{text(day.method_note)}</p>
        <Basis path="day.day_ganzhi" value={text(day.day_ganzhi)} />
      </section>
      <section className="section">
        <h2>大运</h2>
        <div className="luck-timeline" tabIndex={0} role="region" aria-label="大运时间线，可左右滚动">
          {rows(data.dayun).map((item, index) => (
            <article className="luck-step" key={index}>
              <p className="meta">
                {text(item.start_year)}–{text(item.end_year)}
              </p>
              <p className="luck-glyph">{text(item.ganzhi)}</p>
              <p className="meta">起始年龄 {text(item.start_age) || '未提供'}</p>
            </article>
          ))}
        </div>
        {!rows(data.dayun).length && <p className="meta">暂无大运字段。</p>}
      </section>
      <Disclosure title="所选日期的年、月快照">
        {['target_liunian', 'target_liuyue'].map((field) => (
          <section key={field}>
            <h3>{field === 'target_liunian' ? '流年' : '流月'}</h3>
            {rows(data[field]).map((item, index) => (
              <p key={index}>
                {text(item.year) || text(item.month)} {text(item.ganzhi)} {text(item.period_start)}{' '}
                {text(item.period_end_exclusive)}
              </p>
            ))}
          </section>
        ))}
      </Disclosure>
    </div>
  );
}
export function ZiweiData({ data }: { data: Record<string, unknown> }) {
  return (
    <section className="section">
      <h2>紫微宫位</h2>
      <p className="meta">{text(data.wuxing_ju)}</p>
      <div className="people-grid">
        {rows(data.palaces).map((palace, index) => (
          <article className="profile-item" key={index}>
            <h3>
              {text(palace.name)} · {text(palace.ganzhi)}
            </h3>
            <p>
              {rows(palace.major)
                .map((star) => `${text(star.name)} ${text(star.brightness)}`)
                .join('、') || '主星字段未提供'}
            </p>
            <p className="small-text secondary-text">
              {rows(palace.minor)
                .map((star) => text(star.name))
                .join('、')}
            </p>
            <p className="meta">
              {rows(palace.linked_palaces)
                .map((linked) => `${text(linked.relation)} ${text(linked.name)}`)
                .join('；')}
            </p>
            <Basis
              path={`palaces.${index}.major`}
              value={rows(palace.major)
                .map((star) => text(star.name))
                .join('、')}
            />
          </article>
        ))}
      </div>
      {!rows(data.palaces).length && <p>没有返回可展示的宫位数据。</p>}
    </section>
  );
}
export function AstroData({ data }: { data: Record<string, unknown> }) {
  const planets = record(data.planets),
    transits = record(data.transits);
  return (
    <div className="stack">
      <section className="section">
        <h2>本命星体</h2>
        {['太阳', '月亮', '水星', '金星', '火星', '木星', '土星', '天王星', '海王星', '冥王星']
          .filter((name) => planets[name])
          .map((name) => {
            const position = record(planets[name]);
            return (
              <article className="list-row row between wrap" key={name}>
                <span>
                  {name} · {text(position.sign)} {text(position.deg)}° · 第{text(position.house) || '未知'}宫
                </span>
                <Basis path={`planets.${name}`} value={`${text(position.sign)} ${text(position.longitude)}°`} />
              </article>
            );
          })}
      </section>
      <section className="section">
        <h2>宫头</h2>
        {rows(data.houses).map((house, index) => (
          <p key={index}>
            第{text(house.house)}宫 · {text(house.sign)} {text(house.deg)}°
          </p>
        ))}
      </section>
      <Disclosure title="相位与行运快照">
        <h3>本命相位</h3>
        {rows(data.aspects).map((item, index) => (
          <p key={index}>
            {text(item.from)} {text(item.aspect)} {text(item.to)} · 容许度 {text(item.orb)}°
          </p>
        ))}
        <h3>所选日期行运</h3>
        <p className="meta">
          {text(transits.date)} {text(transits.precision_note)}
        </p>
        {rows(transits.aspects_to_natal).map((item, index) => (
          <p key={index}>
            {text(item.from)} {text(item.aspect)} {text(item.to)} · {text(item.orb)}°
          </p>
        ))}
      </Disclosure>
    </div>
  );
}
