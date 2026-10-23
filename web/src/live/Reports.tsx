import { useResource } from '../api/useResource';
import { Markdown } from '../components/Markdown';
import { Disclosure } from '../components/ui/Controls';
import { record, ResourceState, text } from './common';
import { reportNames } from './ReportSchedule';
import type { ReportKind } from './types';

type Report = { id: string; kind?: string; type?: string; date?: string; guidance?: unknown; content?: string };
export default function Reports() {
  const query = useResource<Report[]>('/api/reports');
  const date = new URLSearchParams(location.hash.split('?')[1]).get('date');
  const list = query.data?.filter((item) => !date || item.date === date);
  return (
    <div className="page" data-page="settings">
      <header className="page-heading">
        <h1>报告归档</h1>
        <p className="small-text secondary-text">{date ? `查看 ${date} 的存档` : '查看已保存的报告正文。'}</p>
        <a className="text-link quiet-link" href="#/settings/reports">
          报告与提醒设置
        </a>
      </header>
      <ResourceState
        loading={query.isPending}
        error={query.error}
        retry={() => {
          void query.refetch();
        }}
      />
      {list?.length === 0 && <p>暂时没有{date ? '这一天的' : ''}报告存档。</p>}
      {list?.map((item) => {
        const guidance = record(item.guidance);
        const answer = text(guidance.answer) || item.content || '';
        const kind = item.kind && Object.hasOwn(reportNames, item.kind) ? reportNames[item.kind as ReportKind] : '报告';
        return (
          <article className="report-preview" key={item.id}>
            <p className="meta">
              {item.date} · {kind}
            </p>
            {answer ? <Markdown text={answer} /> : <p>此存档没有可展示的正文。</p>}
            {typeof guidance.professional_appendix === 'string' && guidance.professional_appendix && (
              <Disclosure title="专业附录">
                <Markdown text={guidance.professional_appendix} />
              </Disclosure>
            )}
          </article>
        );
      })}
    </div>
  );
}
