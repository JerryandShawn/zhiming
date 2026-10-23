import { LockKeyhole } from 'lucide-react';
import { Tag } from '../components/ui/Controls';
import { useSpacesDemo } from './store';
import './common.css';

export default function MemoryPreview() {
  const data = useSpacesDemo((state) => state.data);
  return (
    <div className="page spaces-memory" data-page="me" data-runtime="spaces-demo">
      <header className="page-heading">
        <h1>关于我 · 分区记忆</h1>
        <p className="secondary-text">把生活放回各自的脉络里。下面都是合成样例。</p>
        <a className="text-link quiet-link" href="#/organize">
          审阅旧对话整理建议
        </a>
      </header>
      <div className="spaces-memory-grid">
        {data.spaces
          .filter((space) => !space.hidden)
          .sort((a, b) => a.order - b.order)
          .map((space) => {
            const memories = data.memories.filter((item) => item.spaceId === space.id);
            const people = data.people.filter((item) => item.spaceId === space.id);
            const cases = data.cases.filter((item) => item.spaceId === space.id);
            return (
              <section className="section spaces-memory-group" key={space.id} aria-label={`${space.name}记忆分组`}>
                <div className="row between wrap">
                  <h2 className="row">
                    {space.sensitive && <LockKeyhole className="icon small" role="img" aria-label="敏感区" />}
                    {space.name}
                  </h2>
                  <Tag>{memories.length} 条记忆</Tag>
                </div>
                {space.sensitive && <p className="meta">敏感区 · 正式接入后，新记忆需先确认，锁屏预览不显示细节。</p>}
                <h3>记忆</h3>
                {memories.length ? (
                  <ul>
                    {memories.map((memory) => (
                      <li key={memory.id}>{memory.text}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="meta">此区暂无记忆样例。</p>
                )}
                <h3>重要的人</h3>
                {people.length ? (
                  <ul>
                    {people.map((person) => (
                      <li key={person.id}>
                        {person.name} · {person.relation}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="meta">此区暂无人物样例。</p>
                )}
                <h3>事项</h3>
                {cases.length ? (
                  <ul>
                    {cases.map((item) => (
                      <li key={item.id}>
                        <a
                          className="text-link quiet-link"
                          href={`#/chat?space=${encodeURIComponent(space.id)}&topic=${encodeURIComponent(item.topicId ?? '')}`}>
                          {item.title}
                        </a>
                        <span className="meta"> · {item.status}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="meta">此区暂无进行中的事项。</p>
                )}
                <a className="text-link quiet-link" href={`#/chat?space=${encodeURIComponent(space.id)}`}>
                  进入这个区的对话
                </a>
              </section>
            );
          })}
      </div>
    </div>
  );
}
