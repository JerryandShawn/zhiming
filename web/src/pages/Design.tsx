import { useState } from 'react';
import { Check, ImagePlus } from 'lucide-react';
import {
  Button,
  Disclosure,
  IconButton,
  Input,
  Seal,
  Segmented,
  Switch,
  Tag,
  Textarea,
} from '../components/ui/Controls';
import { EmptyState, ErrorBanner, Panel, Skeleton } from '../components/ui/Overlays';
import {
  AskCard,
  AssistantMessage,
  CitationChip,
  Composer,
  DaySeparator,
  DecisionCard,
  MemoryReceipt,
  ReviewBadge,
  StreamingText,
  ToolStatusLine,
  UserMessage,
} from '../components/Messages';
import { ElementBar, LuckTimeline, PillarColumn, StrengthCompare } from '../components/Charts';
import { MiniCalendar, NowCard } from '../components/Calendar';
import { SpreadLayout } from '../components/TarotCards';
import { useUi } from '../state';

function FormExamples() {
  const [on, setOn] = useState(true);
  const [tab, setTab] = useState('默认');
  return (
    <section className="design-section">
      <h2>控件与交互状态</h2>
      <div className="stack">
        <div className="row wrap">
          <Button variant="primary">主操作</Button>
          <Button>次操作</Button>
          <Button variant="ghost">轻操作</Button>
          <Panel
            title="确认删除？"
            description="这是合成样例，不会删除资料。"
            trigger={<Button variant="destructive">删除</Button>}>
            <p>危险操作使用图标与明确文案，并再次确认。</p>
          </Panel>
        </div>
        <div className="row wrap">
          <Button disabled>暂不可用</Button>
          <Button loading>处理中</Button>
          <IconButton label="添加图片示例">
            <ImagePlus className="icon" />
          </IconButton>
          <Switch label="示例开关" checked={on} onChange={setOn} />
        </div>
        <div className="design-grid">
          <label className="field">
            普通输入
            <Input placeholder="写一句话…" />
          </label>
          <label className="field">
            错误状态
            <Input defaultValue="还需要补充" aria-invalid="true" aria-describedby="example-error" />
            <span id="example-error" className="field-error">
              内容还在，请补充后重试。
            </span>
          </label>
          <label className="field">
            禁用输入
            <Input disabled defaultValue="暂不可修改" />
          </label>
          <label className="field">
            多行输入
            <Textarea placeholder="慢慢说…" />
          </label>
        </div>
        <Segmented
          label="分段控制示例"
          value={tab}
          onChange={setTab}
          options={['默认', '选中', '另一项'].map((value) => ({ value, label: value }))}
        />
        <div className="row wrap">
          {['neutral', 'rest', 'work', 'festival', 'accent'].map((tone, index) => (
            <Tag key={tone} tone={tone}>
              {['普通', '休息日', '调休上班', '重阳', '日主'][index]}
            </Tag>
          ))}
        </div>
        <div className="row wrap">
          <Panel title="对话框示例" description="按Esc关闭，焦点回到打开按钮。" trigger={<Button>打开对话框</Button>}>
            <Input aria-label="对话框中的输入" />
          </Panel>
          <Panel
            sheet
            title="抽屉示例"
            description="手机为底部抽屉，桌面为右侧抽屉。"
            trigger={<Button>打开抽屉</Button>}>
            <p>更详细的依据放在这里，不挤占主要回答。</p>
          </Panel>
        </div>
      </div>
    </section>
  );
}

function MessageExamples() {
  const [live, setLive] = useState(true);
  return (
    <section className="design-section">
      <h2>消息与回执</h2>
      <DaySeparator gap="隔了2天">10月17日 星期六</DaySeparator>
      <UserMessage time="21:04" feishu>
        周三我有个面试，有点紧张。
      </UserMessage>
      <AssistantMessage revised>
        <p>
          先把想讲的两件事写下来
          <CitationChip />
          ，留出一点慢慢表达的余地。
        </p>
        <MemoryReceipt />
        <div className="row wrap">
          <ReviewBadge pending />
          <ReviewBadge />
        </div>
      </AssistantMessage>
      <MemoryReceipt state="pending" />
      <MemoryReceipt state="undone" />
      <AskCard />
      <DecisionCard />
      <section className="section">
        <div className="row wrap">
          <Button onClick={() => setLive(!live)}>{live ? '完成并折叠步骤' : '查看生成中状态'}</Button>
        </div>
        <ToolStatusLine live={live} />
        <StreamingText text="先说现实的准备，再把传统解释放在旁边。" />
      </section>
      <Composer busy={live} />
    </section>
  );
}

export default function Design() {
  const notify = useUi((state) => state.notify);
  return (
    <div className="page" data-page="__design">
      <header className="page-heading">
        <h1>组件一览</h1>
        <p className="secondary-text small-text">合成样例 · Tab检查焦点，悬停或按下检查反馈。展示页不保存资料。</p>
      </header>
      <section>
        <h2>宣纸、墨与朱砂</h2>
        <div className="swatches">
          {['paper', 'paper2', 'surface', 'ink', 'cinnabar', 'gold', 'jade', 'line'].map((color) => (
            <div key={color}>
              <div className={`swatch ${color}`} />
              <p className="meta">{color}</p>
            </div>
          ))}
        </div>
        <div className="row wrap section">
          <Seal size="large" />
          <Seal />
          <Seal size="small" />
          <Check className="icon jade-text" />
          <p className="greeting-voice">一张安静的宣纸，一位说话有分寸的老朋友。</p>
        </div>
      </section>
      <FormExamples />
      <MessageExamples />
      <section className="design-section">
        <h2>时间与命盘</h2>
        <div className="design-grid">
          <div>
            <NowCard />
            <MiniCalendar />
          </div>
          <div>
            <PillarColumn />
            <ElementBar />
            <StrengthCompare />
            <LuckTimeline />
          </div>
        </div>
      </section>
      <section className="design-section">
        <h2>牌阵与牌背</h2>
        <SpreadLayout faceUp={false} />
        <SpreadLayout />
        <Disclosure title="其他牌阵" count="单张与A/B五张">
          <SpreadLayout layout="focus1" />
          <SpreadLayout layout="choice5" />
        </Disclosure>
      </section>
      <section className="design-section">
        <h2>空、加载与错误</h2>
        <Skeleton label="正在展开记录" />
        <ErrorBanner action={() => notify('仅演示重试状态，没有发起网络请求。')}>
          这次没连上明镜的大脑。你的话没有丢，可以再试一次。
        </ErrorBanner>
        <EmptyState text="还没有抽过牌。想问点什么？" action="开始" href="#/tarot" />
        <Button onClick={() => notify()}>查看提示</Button>
      </section>
    </div>
  );
}
