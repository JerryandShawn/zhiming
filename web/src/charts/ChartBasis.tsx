import type { ReactElement, ReactNode } from 'react';
import { Panel } from '../components/ui/Overlays';

export function ChartBasis({
  title,
  path,
  system,
  date,
  trigger,
  children,
}: {
  title: string;
  path: string;
  system: string;
  date: string;
  trigger: ReactElement;
  children: ReactNode;
}) {
  const selection = new URLSearchParams({ system, key: path, focus: path, date });
  return (
    <Panel title={title} description="只解释本次返回的盘面字段；象征结构不等于现实结论。" trigger={trigger} sheet>
      <div className="stack small">
        {children}
        <p className="meta">依据字段：{path}</p>
        <a className="button secondary" href={`#/chat?${selection.toString()}`}>
          带着这项依据问明镜
        </a>
      </div>
    </Panel>
  );
}
