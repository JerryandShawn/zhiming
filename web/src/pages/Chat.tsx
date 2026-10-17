import { useState } from 'react';
import { EyeOff } from 'lucide-react';
import { NowCard } from '../components/Calendar';
import {
  AssistantMessage,
  AskCard,
  CitationChip,
  Composer,
  DaySeparator,
  ExampleAnswer,
  MemoryReceipt,
  ToolStatusLine,
  UserMessage,
} from '../components/Messages';
import { Disclosure, Switch } from '../components/ui/Controls';

export default function Chat() {
  const [privateMode, setPrivate] = useState(false);
  return (
    <div className="page chat-page" data-page="chat">
      <h1 className="sr-only">和明镜对话</h1>
      <div className="chat-layout">
        <div className="chat-main">
          <div className="chat-messages">
            <div className="chat-inner">
              <DaySeparator>10月15日 星期四</DaySeparator>
              <UserMessage time="21:04" feishu>
                周三我有个面试，有点紧张
              </UserMessage>
              <AssistantMessage time="21:05">
                <ExampleAnswer />
              </AssistantMessage>
              <DaySeparator gap="隔了2天">今天 10月17日 星期六</DaySeparator>
              <UserMessage time="10:30">那天对我来说怎么样？顺便说下，我最近身体不太好，在吃药调理。</UserMessage>
              <AssistantMessage revised>
                <ToolStatusLine />
                <p>
                  周三是戊辰日
                  <CitationChip />
                  ，对你（丁火日主）来说是「伤官」日：
                  脑子快、表达欲强，适合把想法讲出来。要留意的是别急着反驳面试官，先听完再说。
                </p>
                <Disclosure title="命理依据" count="按流日十神看">
                  <p className="small-text">这是传统解释的合成展示，现实准备仍是关键。</p>
                </Disclosure>
                <AskCard />
                <MemoryReceipt state="pending" />
              </AssistantMessage>
            </div>
          </div>
          <Composer />
        </div>
        <aside className="chat-aside">
          <NowCard />
          <section>
            <h2>这轮用到的</h2>
            <p className="list-row small-text">
              周三10月21日 · 戊辰 · 伤官
              <br />
              <span className="meta">按流日十神看 · 合成示例</span>
            </p>
            <p className="list-row small-text">
              “有点紧张” · 面试安排
              <br />
              <span className="meta">你在10月15日飞书上说的</span>
            </p>
          </section>
          <section>
            <h2>进行中的事</h2>
            {['跳槽', '考研准备'].map((text, index) => (
              <label className="setting-row small-text" key={text}>
                <span>{text}</span>
                <input type="checkbox" defaultChecked={!index} />
              </label>
            ))}
          </section>
          <div className="row between">
            <span className="row small-text">
              <EyeOff className="icon" />
              无痕模式
            </span>
            <Switch label="无痕模式" checked={privateMode} onChange={setPrivate} />
          </div>
        </aside>
      </div>
    </div>
  );
}
