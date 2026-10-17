import { useState } from 'react';
import { ChevronRight, EyeOff, Laptop, ShieldCheck } from 'lucide-react';
import { Button, Input, Segmented, Switch } from '../components/ui/Controls';
import { Panel } from '../components/ui/Overlays';
import { useUi, type Theme } from '../state';

function ReportSettings() {
  const [enabled, setEnabled] = useState([true, true, false, false]);
  const notify = useUi((state) => state.notify);
  return (
    <section className="setting-group">
      <h2>晨报与周期报告</h2>
      <p className="meta">按北京时间发送，提前15分钟准备。</p>
      {['晨报', '周报', '月报', '季报'].map((name, index) => (
        <div className="setting-row" key={name}>
          <Panel
            sheet
            title={`${name}时间`}
            description="这里展示合成设置，不会改变真实发送计划。"
            trigger={
              <button className="row grow">
                <span className="grow">
                  <span>{name}</span>
                  <span className="meta block-text">{index ? '下一期 · 周一07:00' : '下一期 · 明天07:00'}</span>
                </span>
                <ChevronRight className="icon" />
              </button>
            }>
            <div className="stack">
              <label className="field">
                发送时间
                <Input type="time" defaultValue="07:00" />
              </label>
              <p className="meta">北京时间 · 提前15分钟准备</p>
              {index === 1 && (
                <label className="field">
                  星期
                  <select className="select" defaultValue="1">
                    {['一', '二', '三', '四', '五', '六', '日'].map((day, number) => (
                      <option key={day} value={number + 1}>
                        星期{day}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {index > 1 && (
                <label className="field">
                  日期
                  <Input type="number" min="1" max="31" defaultValue="1" />
                </label>
              )}
              <Button variant="primary" onClick={() => notify()}>
                保存时间
              </Button>
            </div>
          </Panel>
          <Switch
            label={`开启${name}`}
            checked={enabled[index]}
            onChange={(value) => setEnabled(enabled.map((item, i) => (i === index ? value : item)))}
          />
        </div>
      ))}
      <a className="text-link" href="#/reports">
        看以前的报告
        <ChevronRight className="icon small" />
      </a>
    </section>
  );
}

function ContactSettings() {
  const [follow, setFollow] = useState(true);
  const [limit, setLimit] = useState('2');
  return (
    <section className="setting-group">
      <h2>主动联系</h2>
      <div className="setting-row">
        <span>事情有进展时问问我</span>
        <Switch label="跟进开关" checked={follow} onChange={setFollow} />
      </div>
      <div className="setting-row wrap">
        <span>每天最多</span>
        <Segmented
          label="每天最多联系次数"
          options={['1', '2', '3'].map((value) => ({ value, label: `${value}次` }))}
          value={limit}
          onChange={setLimit}
        />
      </div>
      <div className="setting-row wrap">
        <span>免打扰</span>
        <div className="row">
          <Input aria-label="免打扰开始时间" type="time" defaultValue="22:00" />
          <span>至</span>
          <Input aria-label="免打扰结束时间" type="time" defaultValue="08:00" />
        </div>
      </div>
    </section>
  );
}

function Archive() {
  return (
    <div className="page" data-page="settings">
      <header className="page-heading">
        <h1>报告归档</h1>
        <p className="small-text secondary-text">把以前的提醒，留在这里慢慢看。</p>
      </header>
      <article className="report-preview">
        <p className="meta">10月17日 星期六 · 晨报</p>
        <h2>周六好，阿远</h2>
        <p>明天重阳，记得给家里打个电话。</p>
        <section className="section">
          <h3>这几天的安排</h3>
          <p>10月21日（周三）面试。今天可以先整理两段想讲清楚的经历。</p>
        </section>
        <section className="section">
          <h3>今日流日</h3>
          <p>甲子日，适合请教前辈、看书充电。现实准备优先。</p>
        </section>
        <a href="#/settings/reports" className="text-link">
          报告与提醒设置
        </a>
      </article>
    </div>
  );
}

export default function Settings() {
  const theme = useUi((state) => state.theme);
  const setTheme = useUi((state) => state.setTheme);
  const notify = useUi((state) => state.notify);
  const [incognito, setIncognito] = useState(false);
  if (location.hash.startsWith('#/reports')) return <Archive />;
  return (
    <div className="page" data-page="settings">
      <header className="page-heading desktop-heading">
        <h1>设置</h1>
      </header>
      <div className="page-grid">
        <div>
          <ReportSettings />
          <ContactSettings />
          <section className="setting-group">
            <h2>模型</h2>
            <div className="setting-row">
              <span>当前主模型</span>
              <span className="small-text">Kimi · k3</span>
            </div>
            <div className="setting-row">
              <span>评审模型</span>
              <span className="small-text">Kimi · 独立复核</span>
            </div>
          </section>
        </div>
        <aside>
          <section className="setting-group">
            <h2>外观</h2>
            <Segmented<Theme>
              label="外观主题"
              value={theme}
              onChange={setTheme}
              options={[
                { value: 'system', label: '跟随系统' },
                { value: 'light', label: '宣纸' },
                { value: 'dark', label: '夜墨' },
              ]}
            />
          </section>
          <section className="setting-group">
            <h2>设备与登录</h2>
            <div className="setting-row">
              <div className="row">
                <Laptop className="icon" />
                <div>
                  <p>这台电脑</p>
                  <p className="meta">今天使用 · 合成设备</p>
                </div>
              </div>
              <Button variant="ghost" onClick={() => notify()}>
                管理
              </Button>
            </div>
            <Button variant="ghost" onClick={() => notify()}>
              退出登录
            </Button>
          </section>
          <section className="setting-group">
            <h2>隐私</h2>
            <div className="setting-row">
              <span className="row">
                <EyeOff className="icon" />
                无痕模式
              </span>
              <Switch label="设置中的无痕模式" checked={incognito} onChange={setIncognito} />
            </div>
            <p className="meta">无痕对话不进入长期记忆。</p>
            <a className="row-link small-text" href="#/me?section=memory">
              <span>让明镜忘掉某段时间</span>
              <ChevronRight className="icon" />
            </a>
            <p className="meta row">
              <ShieldCheck className="icon small" />
              你的资料，由你决定。
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
