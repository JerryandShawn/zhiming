import { publicChatText } from '../../chat/publicProjection';
import { Button } from '../../components/ui/Controls';
import { Sources } from './Sources';
import type { AboutMePort, AboutMeSnapshot } from './types';
import type { OpenMeView } from './views';

export function OtherTabs({
  tab,
  snapshot,
  port,
  open,
}: {
  tab: string;
  snapshot: AboutMeSnapshot;
  port: AboutMePort;
  open: OpenMeView;
}) {
  if (tab === 'people')
    return (
      <section className="section stack" aria-label="重要的人列表">
        <h2>重要的人</h2>
        <p className="meta">只整理你明确说过的关系与经历，不替他人建立出生档案。</p>
        <div className="night-me-card-grid">
          {snapshot.people.map((person) => {
            const count = snapshot.memories.filter(
              (item) => item.status === 'active' && person.memoryIds.includes(item.id),
            ).length;
            return (
              <button
                className="person"
                key={person.id}
                data-person-id={person.id}
                onClick={(event) => open({ kind: 'person', item: person }, event.currentTarget)}>
                <h3>{publicChatText(person.name)}</h3>
                <p className="meta">
                  {publicChatText(person.relation)} · {count} 条相关记忆
                </p>
              </button>
            );
          })}
        </div>
        {!snapshot.people.length && <p className="night-me-empty">还没有已确认的人物关系。</p>}
      </section>
    );
  if (tab === 'timeline') {
    const months = [...new Set(snapshot.timeline.map((item) => item.at.slice(0, 7)))].sort().reverse();
    return (
      <section className="section stack" aria-label="时间线">
        <h2>你经历过的事</h2>
        {months.map((month) => (
          <section key={month} className="stack small">
            <h3>{month.replace('-', ' 年 ')} 月</h3>
            <div className="night-me-timeline stack">
              {snapshot.timeline
                .filter((item) => item.at.startsWith(month))
                .map((item) => (
                  <article key={item.id} data-timeline-id={item.id}>
                    <p className="meta">{item.at.slice(5, 10).replace('-', '/')}</p>
                    <p>{publicChatText(item.text)}</p>
                    <Sources port={port} refs={item.sourceRefs} />
                  </article>
                ))}
            </div>
          </section>
        ))}
        {!months.length && <p className="night-me-empty">还没有已确认的情景记忆。</p>}
      </section>
    );
  }
  return (
    <section className="section stack" aria-label="符号词典">
      <h2>你自己的联想</h2>
      <p className="meta">这里只保留你自述的联想，不把它当作预言。</p>
      {snapshot.dictionary
        .filter((item) => item.status === 'active')
        .map((item) => (
          <article key={item.id} className="night-me-item" data-symbol-id={item.id} data-revision={item.revision}>
            <h3>{publicChatText(item.symbol)}</h3>
            <p>{publicChatText(item.text)}</p>
            <Sources port={port} refs={item.sourceRefs} />
            <Button variant="ghost" onClick={(event) => open({ kind: 'symbol-delete', item }, event.currentTarget)}>
              删除这个联想
            </Button>
          </article>
        ))}
      {!snapshot.dictionary.some((item) => item.status === 'active') && (
        <p className="night-me-empty">还没有你确认过的个人联想。</p>
      )}
    </section>
  );
}
