import { useId, useState, type ReactNode } from 'react';
import { PenLine, Send } from 'lucide-react';
import { Seal } from './ui/Controls';

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
