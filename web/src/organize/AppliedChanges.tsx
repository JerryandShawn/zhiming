import { useMemo, useState } from 'react';
import { Button, Checkbox } from '../components/ui/Controls';
import type { AppliedField, FieldKey, OrganizeSnapshot } from './types';

export function fieldKey(field: FieldKey) {
  return JSON.stringify([field.collection, field.entity_id, field.field]);
}

export default function AppliedChanges({
  snapshot,
  busy,
  onRevert,
}: {
  snapshot: OrganizeSnapshot;
  busy: boolean;
  onRevert: (fields?: FieldKey[]) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const groups = useMemo(() => {
    const result = new Map<string, AppliedField[]>();
    for (const field of snapshot.applied?.fields ?? []) {
      if (field.state !== 'applied') continue;
      const group = result.get(field.group_id) ?? [];
      group.push(field);
      result.set(field.group_id, group);
    }
    return [...result.entries()];
  }, [snapshot.applied]);
  if (!snapshot.applied) return null;
  const fields = groups.filter(([id]) => selected.includes(id)).flatMap(([, rows]) => rows);
  return (
    <section className="stack" aria-labelledby="applied-title">
      <h2 id="applied-title">已应用的变更</h2>
      <p className="small-text secondary-text">
        可以整体撤销，也可以只选部分字段。同一片段的区与话题会一起恢复，避免归属不一致。
        后来改过的值会保留，原消息内容始终不变。
      </p>
      <fieldset className="review-fields stack small" disabled={busy}>
        <legend>选择要撤销的字段</legend>
        {groups.map(([id, rows]) => (
          <label className="review-field" key={id} data-field-key={fieldKey(rows[0])}>
            <Checkbox
              label={`选择撤销：${rows[0].label}`}
              checked={selected.includes(id)}
              onChange={(event) =>
                setSelected(event.target.checked ? [...selected, id] : selected.filter((key) => key !== id))
              }
            />
            <span>
              {rows[0].label}
              <span className="meta"> · {rows.length} 项关联变更</span>
            </span>
          </label>
        ))}
        {!groups.length && <p>可撤销的字段已处理完毕。</p>}
      </fieldset>
      <div className="row wrap">
        <Button disabled={busy || !fields.length} onClick={() => onRevert(fields)}>
          撤销所选字段
        </Button>
        <Button disabled={busy || !groups.length} onClick={() => onRevert()}>
          撤销整批整理
        </Button>
      </div>
      {snapshot.conflicts.length > 0 && (
        <p role="status">有 {snapshot.conflicts.length} 处后来修改或仍被引用的字段已保留，没有覆盖新修改。</p>
      )}
    </section>
  );
}
