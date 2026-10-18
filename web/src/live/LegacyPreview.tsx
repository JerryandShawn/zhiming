import { useResource } from '../api/useResource';
import { Button } from '../components/ui/Controls';
import { record, rows, ResourceState, text } from './common';

const paths: Record<string, string> = { people: '/api/graph', timeline: '/api/timeline', dictionary: '/api/dict' };
export default function LegacyPreview({ section }: { section: string }) {
  const query = useResource<unknown>(paths[section] ?? null);
  const graph = record(query.data);
  const items =
    section === 'people' ? rows(graph.persons) : section === 'timeline' ? rows(graph.forecasts) : rows(query.data);
  return (
    <div className="stack">
      <p className="meta">以下仅为旧版未验证存档概况，不作为已确认事实；旧预测结论与应验率不会迁入新版画像。</p>
      <ResourceState
        loading={query.isPending}
        error={query.error}
        retry={() => {
          void query.refetch();
        }}
      />
      {query.data !== undefined && <p>此分区保留 {items.length} 条历史记录。</p>}
      {items.slice(0, 50).map((item, index) => (
        <article className="profile-item" key={index}>
          <p>
            {section === 'people'
              ? text(item.name) || `人物记录 ${index + 1}`
              : section === 'dictionary'
                ? text(item.symbol) || text(item.omen) || `符号记录 ${index + 1}`
                : `历史事件记录 ${index + 1}`}
          </p>
          {section === 'timeline' && typeof item.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(item.date) && (
            <p className="meta">记录日期：{item.date}</p>
          )}
          <p className="meta">旧版未验证记录 · 只读</p>
        </article>
      ))}
      {items.length === 0 && query.data !== undefined && <p>暂无可展示的历史记录。</p>}
      <p className="secondary-text">这些旧记录目前只供查看。</p>
      <Button disabled>修改此分区</Button>
    </div>
  );
}
