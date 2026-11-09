import { useState } from 'react';
import { pendingPayload } from '../api/operations';
import { Button, Textarea } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { useCommand } from './common';
import type { Case, CaseEvent } from './types';

export default function CaseFeedback({
  item,
  revision,
  refreshed,
  onSaved,
}: {
  item: Case;
  revision: number;
  refreshed: () => Promise<void>;
  onSaved: () => void;
}) {
  const scope = `case-event:${item.id}`;
  const pending = pendingPayload<Record<string, unknown>>(scope);
  const [content, setContent] = useState(String(pending?.content ?? ''));
  const [kind, setKind] = useState(String(pending?.kind ?? 'progress'));
  const command = useCommand(scope);
  async function save() {
    const result = await command.submit<CaseEvent>(
      'POST',
      `/api/cases/${encodeURIComponent(item.id)}/events`,
      {
        expected_revision: pending?.expected_revision ?? revision,
        content: content.trim(),
        kind,
      },
      (value) => Boolean(value.id) && Number.isInteger(value.revision) && value.kind === kind,
    );
    if (result) {
      setContent('');
      command.setStatus('进展已保存到此事项。');
      try {
        await refreshed();
        onSaved();
      } catch {
        command.setStatus('进展已保存，最新事项版本读取未完成，请刷新后再提交。');
      }
    }
  }
  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}>
      <h3>记录新的进展</h3>
      <fieldset className="stack" disabled={command.busy || Boolean(pending)}>
        <Select
          label="进展类型"
          value={kind}
          onChange={setKind}
          options={[
            { value: 'progress', label: '进展' },
            { value: 'decided', label: '已作决定' },
            { value: 'acted', label: '已采取行动' },
            { value: 'result', label: '结果反馈' },
            { value: 'completed', label: '已完成' },
            { value: 'rejected_interpretation', label: '解释不符合' },
          ]}
        />
        <label className="field">
          进展原话
          <Textarea required maxLength={16000} value={content} onChange={(event) => setContent(event.target.value)} />
        </label>
      </fieldset>
      <Button type="submit" disabled={command.conflict} loading={command.busy}>
        {pending ? '重试原进展' : '保存进展'}
      </Button>
      {command.conflict && (
        <Button
          onClick={() =>
            void refreshed()
              .then(command.unlock)
              .catch(() => command.setStatus('最新事项读取未完成，进展草稿仍保留。'))
          }>
          读取最新事项，保留进展草稿
        </Button>
      )}
      <p role="status">{command.status}</p>
    </form>
  );
}
