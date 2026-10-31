import { useState } from 'react';
import { BookOpen, CircleAlert } from 'lucide-react';
import { Button, Disclosure, Seal, Tag } from './ui/Controls';
import { Panel } from './ui/Overlays';

const pillars = [
  {
    name: '年柱',
    spirit: '正印',
    sky: '甲',
    ground: '戌',
    skyTone: 'wood',
    groundTone: 'earth',
    hidden: '戊 · 辛 · 丁',
    sound: '山头火',
  },
  {
    name: '月柱',
    spirit: '比肩',
    sky: '丁',
    ground: '卯',
    skyTone: 'fire',
    groundTone: 'wood',
    hidden: '乙',
    sound: '炉中火',
  },
  {
    name: '日柱',
    spirit: '日主',
    sky: '丁',
    ground: '酉',
    skyTone: 'fire',
    groundTone: 'metal',
    hidden: '辛',
    sound: '山下火',
  },
  {
    name: '时柱',
    spirit: '正印',
    sky: '甲',
    ground: '辰',
    skyTone: 'wood',
    groundTone: 'earth',
    hidden: '戊 · 乙 · 癸',
    sound: '覆灯火',
  },
];

export function PillarColumn() {
  return (
    <div className="pillars">
      {pillars.map((pillar) => (
        <div className={`pillar ${pillar.name === '日柱' ? 'day-master' : ''}`} key={pillar.name}>
          <p className="meta">{pillar.name}</p>
          <p className="meta secondary-text">{pillar.spirit}</p>
          <Panel
            sheet
            title={`${pillar.sky}${pillar.ground} · ${pillar.name}`}
            description="合成盘面中的术语解释，不是人生预测。"
            trigger={
              <button className="pillar-glyphs" aria-label={`查看${pillar.name}${pillar.sky}${pillar.ground}依据`}>
                <span className={pillar.skyTone}>{pillar.sky}</span>
                <span className={pillar.groundTone}>{pillar.ground}</span>
              </button>
            }>
            <p>
              天干{pillar.sky}、地支{pillar.ground}。藏干是{pillar.hidden}。应结合具体口径与现实处境阅读。
            </p>
            <a href="#/chat" className="button secondary">
              问问明镜
            </a>
          </Panel>
          <p className="meta secondary-text">{pillar.hidden}</p>
          <p className="meta">{pillar.sound}</p>
        </div>
      ))}
    </div>
  );
}

export function ElementBar() {
  return (
    <section className="section">
      <h2>五行构成</h2>
      <div className="element-bar" role="img" aria-label="木3、火2、土2、金1、水0">
        <span className="wood-bg" />
        <span className="fire-bg" />
        <span className="earth-bg" />
        <span className="metal-bg" />
      </div>
      <p className="meta row wrap">
        {['木3', '火2', '土2', '金1', '水0'].map((text, index) => (
          <span key={text} className={['wood', 'fire', 'earth', 'metal', 'water'][index]}>
            {text}
          </span>
        ))}
      </p>
      <p className="meta">这是构成计数，不等于旺衰。</p>
    </section>
  );
}

export function StrengthCompare() {
  return (
    <section className="section">
      <h2>旺衰</h2>
      <div className="strength-grid">
        {['月令通根打分', '得令 / 得地 / 得势'].map((method) => (
          <div key={method}>
            <h3 className="small-text">{method}</h3>
            <Tag>偏强 · 示例</Tag>
            <p className="meta">示例分数：62</p>
            <Disclosure title="依据" count="2条">
              <p className="small-text">按季节、根气与相助关系交叉查看， 示例结论不替代完整计算。</p>
            </Disclosure>
          </div>
        ))}
      </div>
      <p className="meta">两种方法结论一致</p>
    </section>
  );
}

export function LuckTimeline() {
  return (
    <section className="section">
      <h2>大运</h2>
      <div className="luck-timeline" tabIndex={0} role="region" aria-label="大运时间线，可左右滚动">
        {['戊辰', '己巳', '庚午', '辛未', '壬申', '癸酉'].map((text, index) => (
          <div className={`luck-step ${index === 2 ? 'now' : ''}`} key={text}>
            <p className="meta">
              {index === 2 ? '现在' : `${9 + index * 10}岁`} · {2002 + index * 10}
            </p>
            <p className="luck-glyph">{text}</p>
            <p className="meta">{['伤官', '食神', '正财', '偏财', '正官', '七杀'][index]}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export function PalaceGrid() {
  const [grid, setGrid] = useState(false);
  const palaces = ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄', '迁移', '交友', '官禄', '田宅', '福德', '父母'];
  return (
    <>
      <div className="row between">
        <h2>十二宫</h2>
        <Button onClick={() => setGrid(!grid)}>{grid ? '宫位列表' : '网格'}</Button>
      </div>
      <div
        className={grid ? 'palace-grid' : 'palace-list'}
        tabIndex={grid ? 0 : undefined}
        role="region"
        aria-label="十二宫盘面，网格可左右滚动">
        {palaces.map((name, index) => (
          <Disclosure key={name} title={name} count={['天府', '天梁', '太阴', '紫微'][index % 4]}>
            <p className="small-text">本命星曜合成示例。</p>
            <Tag tone={index % 2 ? 'festival' : 'rest'}>{index % 2 ? '化科' : '化禄'}</Tag>
          </Disclosure>
        ))}
        <div className="palace-center">
          <Seal />
          <p>阿远 · 本命</p>
          <p className="meta">十二宫合成示例</p>
        </div>
      </div>
      <p className="meta row">
        <CircleAlert className="icon small" />
        宫位解释需要结合全盘，不能单看一颗星。
      </p>
    </>
  );
}

export function AstroWheel() {
  const names = ['日', '月', '水', '金', '火', '木', '土', '天', '海', '冥'];
  return (
    <>
      <svg className="astro-wheel" viewBox="0 0 400 400" role="img" aria-label="合成星盘示意">
        <circle cx="200" cy="200" r="180" fill="none" stroke="var(--line-strong)" />
        <circle cx="200" cy="200" r="145" fill="none" stroke="var(--line-strong)" />
        {Array.from({ length: 12 }, (_, index) => (
          <line
            key={index}
            x1="200"
            y1="200"
            x2={200 + Math.cos((index * Math.PI) / 6) * 180}
            y2={200 + Math.sin((index * Math.PI) / 6) * 180}
            stroke="var(--line)"
          />
        ))}
        <path d="M80 150L300 105L210 330Z" fill="none" stroke="var(--jade)" />
        <path d="M80 150L320 270L100 295" fill="none" stroke="var(--cinnabar)" />
        {names.map((name, index) => (
          <text
            key={name}
            x={200 + Math.cos(index * 0.61) * 160}
            y={205 + Math.sin(index * 0.61) * 160}
            textAnchor="middle"
            fill="var(--ink)">
            {name}
          </text>
        ))}
      </svg>
      <Disclosure title="行星与相位" count="10颗行星">
        <p>太阳双鱼、月亮白羊为合成展示。和谐相位以玉色，紧张相位以朱砂表示。</p>
      </Disclosure>
      <Disclosure title="计算口径" count="示例">
        <p className="row">
          <BookOpen className="icon" />
          真实盘面等待后续计算接口接入。
        </p>
      </Disclosure>
    </>
  );
}
