import { ChevronRight } from 'lucide-react';
import { Seal, Tag, Disclosure } from '../components/ui/Controls';
import { MiniCalendar, NowCard } from '../components/Calendar';

export default function Today() {
  return (
    <div className="page" data-page="today">
      <div className="page-grid">
        <div>
          <h1 className="today-date">10月17日 · 星期六</h1>
          <p className="small-text secondary-text">农历九月初八 · 丙午年 戊戌月 甲子日</p>
          <div className="row wrap today-tags">
            <Tag tone="rest">周末休息</Tag>
            <Tag tone="festival">明天重阳</Tag>
            <Tag tone="festival">霜降还有6天</Tag>
          </div>
          <div className="greeting">
            <Seal size="large" />
            <div>
              <p className="greeting-voice">
                周六好，阿远。明天重阳，记得给家里打个电话。 周三的面试，今天可以先把想讲的两件事写下来。
              </p>
              <p className="meta">明镜 · 07:00</p>
            </div>
          </div>
          <section className="section">
            <h2>今天和这几天</h2>
            <ul className="plain-list">
              <li className="event-row">
                <span className="small-text secondary-text">周三 10月21日</span>
                <span className="event-name">面试</span>
                <Tag>晚上我来问你</Tag>
              </li>
              <li className="event-row">
                <span className="small-text secondary-text">周五 10月23日</span>
                <span className="event-name gold-text">霜降 · 17:38交节</span>
              </li>
            </ul>
          </section>
          <section className="section">
            <h2>今日流日</h2>
            <h3>甲子日 · 对你是「正印」日</h3>
            <p className="secondary-text">适合请教前辈、看书充电，把面试要讲的故事理一理。</p>
            <a className="text-link" href="#/chart?tab=bazi">
              看依据
              <ChevronRight className="icon small" />
            </a>
          </section>
        </div>
        <aside className="page-aside today-aside">
          <NowCard />
          <MiniCalendar />
          <section className="section">
            <Disclosure title="黄历" count="宜 纳采 会亲友 沐浴">
              <p className="small-text">黄历仅作传统文化参考，现实安排优先。</p>
            </Disclosure>
          </section>
          <section className="section">
            <div className="row between">
              <h2>进行中的事</h2>
              <a href="#/cases" className="text-link quiet-link">
                全部
                <ChevronRight className="icon small" />
              </a>
            </div>
            <a href="#/cases" className="row-link">
              <span>跳槽</span>
              <span className="meta">上次进展 10月15日</span>
            </a>
          </section>
        </aside>
      </div>
      <div className="today-action">
        <a className="button primary block" href="#/chat">
          和明镜聊聊
        </a>
      </div>
    </div>
  );
}
