import { Disclosure } from '../../components/ui/Controls';
import type { StreamState } from '../types';

function summary(tools: StreamState['tools']) {
  const done = tools.filter((tool) => tool.done);
  const memories = done.filter((tool) => /^(memory_recall|memory_search|memory_get)$/.test(tool.name)).length;
  const calculations = done.filter((tool) => /^(chart_compute|time_context|calendar)$/.test(tool.name)).length;
  const other = done.length - memories - calculations;
  return (
    [
      memories ? `查了 ${memories} 次记忆` : '',
      calculations ? `完成 ${calculations} 次计算` : '',
      other ? `完成 ${other} 个步骤` : '',
    ]
      .filter(Boolean)
      .join(' · ') || '查看本轮步骤'
  );
}
export function ToolProgress({ tools, status, complete }: Pick<StreamState, 'tools' | 'status' | 'complete'>) {
  const running = tools.find((tool) => !tool.done);
  const live = !complete && (status || running?.summary);
  return (
    <div className="tool-progress">
      {live && (
        <p className="tool-status live" role="status">
          <span className="status-dot" aria-hidden="true" />
          {status || running?.summary || '正在核对本轮资料'}
        </p>
      )}
      {tools.length > 0 && (
        <Disclosure title={summary(tools)} count="查看步骤">
          <ol className="small-text">
            {tools.map((tool, index) => (
              <li key={index}>
                {tool.summary || '核对本轮资料'} · {tool.done ? '已完成' : complete ? '未收到完成回执' : '进行中'}
              </li>
            ))}
          </ol>
        </Disclosure>
      )}
    </div>
  );
}
