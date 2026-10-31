import { useResource } from '../api/useResource';
import { Seal } from '../components/ui/Controls';
import { localDate, record, ResourceState, text } from './common';
import type { Case, History } from './types';
import { TodayCalendar } from '../calendar/TodayCalendar';

export default function Today() {
  const date = localDate();
  const cases = useResource<Case[]>('/api/cases?subject_id=self');
  const history = useResource<History[]>('/api/history?session=shared&subject_id=self&limit=4');
  const chart = useResource<Record<string, unknown>>(`/api/chart?date=${date}`);
  const day = record(chart.data?.day);
  const dateLabel = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(new Date());
  return (
    <div className="page" data-page="today">
      <div className="page-grid">
        <div>
          <h1 className="today-date">{dateLabel}</h1>
          <p className="meta">北京时间 · {date}</p>
          <div className="greeting">
            <Seal size="large" />
            <div>
              <p className="greeting-voice">先看看正在进行的事，再从今天能做的一小步开始。</p>
              <p className="meta">资料以你实际确认的记录为准。</p>
            </div>
          </div>
          <section className="section">
            <h2>今日流日</h2>
            <ResourceState
              loading={chart.isPending}
              error={chart.error}
              retry={() => {
                void chart.refetch();
              }}
            />
            {chart.data && (
              <>
                <h3>{text(day.day_ganzhi) || '流日字段尚未提供'}</h3>
                <p className="small-text secondary-text">{text(day.method_note)}</p>
                <a className="text-link quiet-link" href={`#/chart?tab=bazi&date=${date}`}>
                  查看计算依据
                </a>
              </>
            )}
            {chart.error && (
              <a className="text-link quiet-link" href="#/me?section=profile">
                先核对排盘资料
              </a>
            )}
          </section>
          <section className="section">
            <h2>最近对话</h2>
            <ResourceState
              loading={history.isPending}
              error={history.error}
              retry={() => {
                void history.refetch();
              }}
            />
            {history.data?.length ? (
              <p>最近有 {history.data.length} 条对话记录可继续查看。</p>
            ) : (
              history.data && <p>还没有对话记录。</p>
            )}
            <a className="button secondary" href="#/chat">
              查看历史并继续聊
            </a>
          </section>
        </div>
        <aside className="page-aside today-aside">
          <TodayCalendar today={date} />
          <section className="section">
            <h2>进行中的事</h2>
            <ResourceState
              loading={cases.isPending}
              error={cases.error}
              retry={() => {
                void cases.refetch();
              }}
            />
            {cases.data
              ?.filter((item) => item.status === 'open')
              .slice(0, 5)
              .map((item) => (
                <a className="row-link" href={`#/chat?case=${encodeURIComponent(item.id)}`} key={item.id}>
                  <span>{item.title}</span>
                  <span className="meta">继续这件事</span>
                </a>
              ))}
            {cases.data?.filter((item) => item.status === 'open').length === 0 && (
              <p className="meta">暂无进行中的事项。</p>
            )}
            <a className="text-link quiet-link" href="#/cases">
              管理全部事项
            </a>
          </section>
          <section className="section">
            <h2>安排与跟进</h2>
            <p className="meta">自动跟进安排正在准备。你可以先到事项中记录实际进展。</p>
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
