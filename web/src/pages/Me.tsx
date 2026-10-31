import { useState } from 'react';
import { ChevronRight, MoreHorizontal, Settings2 } from 'lucide-react';
import { MemoryReceipt } from '../components/Messages';
import { Button, IconButton, Input, Seal, Segmented, Tag, Textarea } from '../components/ui/Controls';
import { Panel } from '../components/ui/Overlays';
import { useUi } from '../state';

const sections = ['画像', '记忆', '待确认', '重要的人', '时间线', '符号词典'];
const aliases: Record<string, string> = {
  memory: '记忆',
  pending: '待确认',
  people: '重要的人',
  timeline: '时间线',
  dictionary: '符号词典',
};

function Profile() {
  const notify = useUi((state) => state.notify);
  return (
    <div>
      {[
        ['称呼与基本情况', '你希望明镜叫你阿远，目前在准备新的工作机会。'],
        ['现在的生活', '正在准备一次面试，想换到更适合长期发展的团队。'],
        ['在意的事与目标', '希望工作之外也留一点自己的时间。'],
        ['重要的人', '会在节日里惦记家人，明天想给妈妈打个电话。'],
        ['偏好与禁忌', '不喜欢被催着决定，希望留一点独处的时间。'],
        ['沟通偏好', '喜欢先说现实情况，再把几种可能摆出来。'],
        ['命理档案摘要', '丁火日主为合成盘面示例，口径与可信度应到命盘页核对。'],
        ['正在跟进', '10月21日面试，之后再聊聊真实感受。'],
      ].map(([title, text], index) => (
        <section className="section" key={title}>
          <h2>{title}</h2>
          <div className="profile-item">
            <div className="row between">
              <p>{text}</p>
              <Panel
                sheet
                title="修改画像条目"
                description="合成示例：没有连接资料服务，编辑不会保存。"
                trigger={
                  <IconButton label={`编辑${title}`}>
                    <MoreHorizontal className="icon" />
                  </IconButton>
                }>
                <div className="stack">
                  <label className="field">
                    你的说法
                    <Textarea defaultValue={text} />
                  </label>
                  <Button variant="primary" onClick={() => notify()}>
                    保存修改
                  </Button>
                  <Panel
                    title="删除这条画像？"
                    description="删除这条与删除整段来源是两种不同的操作。"
                    trigger={<Button variant="destructive">删除这条</Button>}>
                    <Button variant="destructive" onClick={() => notify()}>
                      确认删除这条
                    </Button>
                  </Panel>
                </div>
              </Panel>
            </div>
            <a href="#/me?section=memory" className="source-link">
              来自10月15日 飞书
              <ChevronRight className="icon small" />
            </a>
            {index === 0 && <Tag>你改过</Tag>}
          </div>
        </section>
      ))}
    </div>
  );
}

function Memories() {
  const [search, setSearch] = useState('');
  const notify = useUi((state) => state.notify);
  return (
    <div className="stack">
      <Input
        type="search"
        aria-label="搜索记忆"
        placeholder="找一件你说过的事…"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div className="row wrap">
        <Tag tone="accent">全部</Tag>
        <Tag>安排</Tag>
        <Tag>偏好</Tag>
      </div>
      {['10月21日有一场面试', '习惯先写下来，再慢慢讲清楚']
        .filter((text) => text.includes(search))
        .map((text) => (
          <article className="profile-item" key={text}>
            <h3>{text}</h3>
            <blockquote className="memory-quote">“周三我有个面试，有点紧张。”</blockquote>
            <p className="meta">10月15日 21:04 · 飞书</p>
            <div className="row wrap">
              <Panel
                title="删除范围"
                description="只删这条不会删除整段来源；删除整段来源会同时清除由它整理出的画像与摘要。"
                trigger={<Button variant="ghost">修改或删除</Button>}>
                <div className="stack">
                  <Button variant="destructive" onClick={() => notify()}>
                    只删这条
                  </Button>
                  <Button variant="destructive" onClick={() => notify()}>
                    删除整段来源
                  </Button>
                  <p className="meta">合成预览，不会执行删除。</p>
                </div>
              </Panel>
            </div>
          </article>
        ))}
    </div>
  );
}

export default function Me() {
  const section = new URLSearchParams(location.hash.split('?')[1]).get('section') ?? '';
  const [tab, setTab] = useState(aliases[section] ?? '画像');
  return (
    <div className="page" data-page="me">
      <header className="profile-heading">
        <Seal size="large" />
        <div className="grow">
          <h1>明镜记得你的126件事</h1>
          <p className="meta">3件待你确认 · 上次整理 今天03:00</p>
        </div>
        <a href="#/settings" className="icon-button" aria-label="设置">
          <Settings2 className="icon" />
        </a>
      </header>
      <div className="route-tabs">
        <Segmented
          label="关于我的分区"
          options={sections.map((value) => ({ value, label: value }))}
          value={tab}
          onChange={setTab}
        />
      </div>
      {tab === '画像' ? (
        <Profile />
      ) : tab === '记忆' ? (
        <section className="section">
          <Memories />
        </section>
      ) : tab === '待确认' ? (
        <section className="section">
          <h2>要不要记住这些？</h2>
          <MemoryReceipt state="pending" />
          <MemoryReceipt state="pending" />
          <p className="meta">旧版资料：暂无待确认条目。</p>
        </section>
      ) : tab === '重要的人' ? (
        <section className="section people-grid">
          {['妈妈', '小林'].map((name) => (
            <Panel
              sheet
              key={name}
              title={name}
              description="合成人物，展示关系与相关记忆。"
              trigger={
                <button className="person">
                  <h2>{name}</h2>
                  <p className="meta">{name === '妈妈' ? '家人' : '朋友'} · 3条相关记忆</p>
                </button>
              }>
              <p>这些记忆来自你明确说过的话，不替他人建立出生档案。</p>
            </Panel>
          ))}
        </section>
      ) : tab === '时间线' ? (
        <section className="section">
          <h2>2026年10月</h2>
          <div className="timeline">
            <article>
              <p className="meta">10月15日</p>
              <p>决定先准备周三的面试。</p>
            </article>
            <article>
              <p className="meta">10月12日</p>
              <p>整理了近期想做的事。</p>
            </article>
          </div>
        </section>
      ) : (
        <section className="section">
          <h2>你自己的联想</h2>
          <div className="profile-item">
            <h3>星星</h3>
            <p>对我来说是“慢一点也没关系”。</p>
            <p className="meta">你的自述 · 合成示例</p>
          </div>
        </section>
      )}
      <footer className="section meta">已经发到飞书的消息无法撤回；删除会同时清除由它整理出的画像与摘要。</footer>
    </div>
  );
}
