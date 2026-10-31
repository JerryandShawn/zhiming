import { ChevronRight, Plus } from 'lucide-react';
import { Button, Input, Tag, Textarea } from '../components/ui/Controls';
import { Panel } from '../components/ui/Overlays';
import { useUi } from '../state';

const cases = [
  {
    name: '跳槽',
    goal: '找到适合长期发展的团队，先把面试准备好。',
    time: '10月15日',
    next: '10月21日晚上',
    status: '进行中',
  },
  {
    name: '考研准备',
    goal: '先完成这个月的复习计划，看看实际节奏。',
    time: '10月12日',
    next: '10月25日',
    status: '进行中',
  },
  { name: '恢复规律作息', goal: '每晚留出一段安静时间，少熬夜。', time: '9月28日', next: '暂无安排', status: '暂停' },
];

function CaseDetail({ name }: { name: string }) {
  const notify = useUi((state) => state.notify);
  return (
    <div className="stack">
      <label className="field">
        目标
        <Textarea defaultValue="先把下一步做好，再决定走多远。" />
      </label>
      <h3>最近进展</h3>
      <div className="timeline">
        <article>
          <p className="meta">10月15日 · 飞书</p>
          <p>决定先参加周三的面试。</p>
        </article>
        <article>
          <p className="meta">10月12日 · 网页</p>
          <p>整理了两段能讲清楚的项目经历。</p>
        </article>
      </div>
      <p className="meta">与「{name}」有关的对话与牌阵会放在这里。</p>
      <a href="#/chat" className="button primary">
        在对话中继续
      </a>
      <div className="row wrap">
        <Button onClick={() => notify()}>暂停</Button>
        <Button onClick={() => notify()}>结束</Button>
      </div>
    </div>
  );
}

export default function Cases() {
  const notify = useUi((state) => state.notify);
  return (
    <div className="page" data-page="cases">
      <header className="page-heading row between">
        <div>
          <h1>进行中的事</h1>
          <p className="small-text secondary-text">把想做的事，慢慢变成有进展的事。</p>
        </div>
        <Panel
          sheet
          title="新建事项"
          description="先写一个具体的小目标。此处是合成界面预览，不写入资料。"
          trigger={
            <Button>
              <Plus className="icon" />
              新建
            </Button>
          }>
          <div className="stack">
            <label className="field">
              标题
              <Input />
            </label>
            <label className="field">
              目标
              <Textarea />
            </label>
            <Button variant="primary" onClick={() => notify()}>
              创建
            </Button>
          </div>
        </Panel>
      </header>
      <div>
        {cases.map((item) => (
          <Panel
            sheet
            key={item.name}
            title={item.name}
            description={item.goal}
            trigger={
              <button type="button" className="row-link full-row">
                <span className="case-body">
                  <span className="row wrap">
                    <span className="case-title">{item.name}</span>
                    <Tag tone={item.status === '进行中' ? 'rest' : 'neutral'}>{item.status}</Tag>
                  </span>
                  <span className="small-text secondary-text">{item.goal}</span>
                  <span className="meta">
                    上次进展 {item.time} · <span className="gold-text">下次跟进 {item.next}</span>
                  </span>
                </span>
                <ChevronRight className="icon" />
              </button>
            }>
            <CaseDetail name={item.name} />
          </Panel>
        ))}
      </div>
    </div>
  );
}
