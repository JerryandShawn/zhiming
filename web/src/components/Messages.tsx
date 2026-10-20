import { useId, useState, type ReactNode } from 'react';
import { BookmarkCheck, PenLine, Send, Undo2 } from 'lucide-react';
import { useReducedMotion } from 'motion/react';
import * as Popover from '@radix-ui/react-popover';
import { Button, Disclosure, Seal, Tag } from './ui/Controls';
import { Markdown } from './Markdown';
import { useUi } from '../state';

export function DaySeparator({ children, gap }: { children: string; gap?: string }) {
  return (
    <div className="day-separator">
      <div>{children}</div>
      {gap && <p className="meta">{gap}</p>}
    </div>
  );
}

export function UserMessage({
  children,
  time,
  feishu = false,
}: {
  children: ReactNode;
  time: string;
  feishu?: boolean;
}) {
  return (
    <article className="user-message" aria-label="你说的">
      <div className="user-bubble">{children}</div>
      <div className="meta row">
        {time}
        {feishu && (
          <>
            <Send className="icon small" aria-hidden="true" />
            飞书
          </>
        )}
      </div>
    </article>
  );
}

export function ReviewBadge({ pending = false }: { pending?: boolean }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  if (pending) return <span className="meta row">复核中</span>;
  return (
    <span
      className="meta row gold-text review-badge"
      tabIndex={0}
      aria-describedby={open ? id : undefined}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(event) => {
        if (event.key === 'Escape') setOpen(false);
      }}>
      <PenLine className="icon small" aria-hidden="true" />
      已修订
      {open && (
        <span role="tooltip" id={id} className="review-tooltip">
          复核后修正了一处说法
        </span>
      )}
    </span>
  );
}

export function AssistantMessage({
  children,
  time = '10:31',
  revised = false,
  pending = false,
}: {
  children: ReactNode;
  time?: string;
  revised?: boolean;
  pending?: boolean;
}) {
  return (
    <article className="assistant-message" aria-label="明镜的回答">
      <header className="row assistant-head">
        <Seal size="small" />
        <span className="meta">明镜 · {time}</span>
        {(revised || pending) && <ReviewBadge pending={pending} />}
      </header>
      <div className="assistant-body">{children}</div>
    </article>
  );
}

export function CitationChip({ number = 1 }: { number?: number }) {
  return (
    <Popover.Root>
      <Popover.Trigger className="citation" aria-label={`查看第${number}条依据`}>
        <span>{number}</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="popover" sideOffset={8} aria-label={`第${number}条依据详情`}>
          <p>10月21日是戊辰日；面试安排来自你之前说的话。</p>
          <p className="meta">合成示例 · 10月15日 · 飞书</p>
          <a className="text-link" href="#/me?section=memory">
            在关于我中查看
          </a>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function ToolStatusLine({ live = false }: { live?: boolean }) {
  if (live)
    return (
      <div className="tool-status live" role="status">
        <span className="status-dot" />
        在算10月21日的流日…
      </div>
    );
  return (
    <Disclosure title="查了1处记忆 · 算了1个日子" count="查看步骤">
      <ol className="small-text">
        <li>核对你在10月15日说的面试安排。</li>
        <li>按流日十神查看10月21日。</li>
      </ol>
    </Disclosure>
  );
}

export function StreamingText({ text }: { text: string }) {
  const reduced = useReducedMotion();
  return (
    <span aria-live="polite" className={reduced ? '' : 'ink-enter'}>
      {text}
    </span>
  );
}

export function MemoryReceipt({ state = 'saved' }: { state?: 'saved' | 'pending' | 'undone' }) {
  const notify = useUi((value) => value.notify);
  if (state === 'undone')
    return (
      <p className="meta row">
        <Undo2 className="icon small" />
        已撤销，不会再提起
      </p>
    );
  if (state === 'pending')
    return (
      <div className="pending-receipt">
        <p>这个比较私人，要不要我记住？</p>
        <p className="meta">最近身体不太好，在吃药调理。</p>
        <div className="row wrap">
          <Button variant="primary" onClick={() => notify()}>
            记住
          </Button>
          <Button onClick={() => notify()}>不用</Button>
          <Button variant="ghost" onClick={() => notify()}>
            以后这类都记
          </Button>
        </div>
      </div>
    );
  return (
    <div className="memory-receipt">
      <span className="row small-text">
        <BookmarkCheck className="icon small jade-text" />
        记下了：10月21日（周三）面试
      </span>
      <Button variant="ghost" onClick={() => notify()}>
        撤销
      </Button>
    </div>
  );
}

export function AskCard() {
  const [selected, select] = useState('');
  return (
    <div className="ask-card">
      <p className="question">这次是技术面，还是谈薪的终面？</p>
      <p className="meta">为什么问：不同轮次要准备的重点不一样</p>
      <div className="ask-options">
        {['技术面', '终面 · 谈薪', '还不确定'].map((option) => (
          <Button
            key={option}
            aria-pressed={selected === option}
            disabled={Boolean(selected)}
            onClick={() => select(option)}>
            {option}
          </Button>
        ))}
        <Button
          variant="ghost"
          disabled={Boolean(selected)}
          onClick={() => document.getElementById('composer-input')?.focus()}>
          我自己说
        </Button>
      </div>
      {selected && <p className="meta">你选了：{selected}</p>}
    </div>
  );
}

export function DecisionCard() {
  const options = ['先准备，再决定', '现在就试着申请'];
  return (
    <div className="decision-options" role="region" aria-label="两种选择的收益与风险" tabIndex={0}>
      {options.map((title, index) => (
        <section className="decision-card" key={title}>
          <h3>{title}</h3>
          <dl>
            {['收益', '代价', '风险', '可逆性', '第一步'].map((label, row) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>
                  {
                    [
                      ['留出准备的余地', '先获得真实反馈'][index],
                      '需要一周时间',
                      '可能错过部分机会',
                      '可以随时调整',
                      '整理两段项目经历',
                    ][row]
                  }
                </dd>
              </div>
            ))}
          </dl>
          <Tag tone="work">待你决定</Tag>
        </section>
      ))}
    </div>
  );
}

export { Composer } from './Composer';

export function ExampleAnswer() {
  return (
    <>
      <Markdown text="紧张说明你在意这次机会，挺正常的。面试前一两天，把你最想让对方记住的**两件事**写下来，比临时背答案管用。" />
      <MemoryReceipt />
    </>
  );
}
