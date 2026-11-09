import { useState } from 'react';
import { api } from '../api/client';
import { pendingPayload } from '../api/operations';
import { useResource } from '../api/useResource';
import { Button, Input, Tag, Textarea } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { Panel } from '../components/ui/Overlays';
import { ResourceState, shownTime, useCommand } from './common';
import type { Case } from './types';
import Feedback from './CaseFeedback';

function CreateCase({ onSaved }: { onSaved: () => void }) {
  const scope = 'case-create:self';
  const pending = pendingPayload<Record<string, unknown>>(scope);
  const [title, setTitle] = useState(String(pending?.title ?? ''));
  const [goal, setGoal] = useState(String(pending?.goal ?? ''));
  const command = useCommand(scope);
  async function save() {
    const result = await command.submit<Case>(
      'POST',
      '/api/cases',
      { title: title.trim(), goal: goal.trim(), subject_id: 'self' },
      (value) => Boolean(value.id) && Number.isInteger(value.revision) && value.status === 'open',
    );
    if (result) {
      setTitle('');
      setGoal('');
      command.setStatus('事项已保存。');
      onSaved();
    }
  }
  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}>
      <fieldset disabled={command.busy || Boolean(pending)} className="stack">
        <label className="field">
          标题
          <Input maxLength={120} required value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <label className="field">
          目标
          <Textarea maxLength={2000} value={goal} onChange={(event) => setGoal(event.target.value)} />
        </label>
      </fieldset>
      <Button type="submit" variant="primary" loading={command.busy}>
        {pending ? '重试创建原事项' : '创建事项'}
      </Button>
      <p role="status">{command.status}</p>
    </form>
  );
}
function CaseDetail({ item, onSaved }: { item: Case; onSaved: () => void }) {
  const scope = `case-edit:${item.id}`;
  const pending = pendingPayload<{
    expected_revision: number;
    changes: { title: string; goal: string; status: string };
  }>(scope);
  const [title, setTitle] = useState(pending?.changes.title ?? item.title);
  const [goal, setGoal] = useState(pending?.changes.goal ?? item.goal ?? item.state?.goal ?? '');
  const [status, setStatus] = useState(pending?.changes.status ?? item.status);
  const [version, setVersion] = useState(pending?.expected_revision ?? item.revision);
  const command = useCommand(scope);
  async function refresh() {
    const records = await api<Case[]>('/api/cases?subject_id=self');
    const latest = records.find((row) => row.id === item.id);
    if (!latest) throw new Error('事项已不可用，请返回列表重新核对。');
    setVersion(latest.revision);
    onSaved();
  }
  async function refreshDraft() {
    try {
      await refresh();
      command.unlock();
    } catch {
      command.setStatus('最新事项读取失败，草稿仍保留。');
    }
  }
  async function save() {
    const result = await command.submit<Case>(
      'PATCH',
      `/api/cases/${encodeURIComponent(item.id)}`,
      {
        expected_revision: version,
        changes: { title: title.trim(), goal: goal.trim(), status },
      },
      (value) => value.id === item.id && Number.isInteger(value.revision) && value.status === status,
    );
    if (result) {
      setVersion(result.revision);
      command.setStatus('事项更正已保存。');
      onSaved();
    }
  }
  return (
    <div className="stack">
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}>
        <fieldset disabled={command.busy || Boolean(pending)} className="stack">
          <label className="field">
            事项名称
            <Input required maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="field">
            事项目标
            <Textarea maxLength={2000} value={goal} onChange={(event) => setGoal(event.target.value)} />
          </label>
          <Select
            label="事项状态"
            value={status}
            onChange={setStatus}
            options={[
              { value: 'open', label: '进行中' },
              { value: 'closed', label: '已关闭' },
            ]}
          />
        </fieldset>
        <Button type="submit" disabled={command.conflict} loading={command.busy}>
          {pending ? '重试原事项更正' : '保存事项更正'}
        </Button>
        {command.conflict && <Button onClick={() => void refreshDraft()}>读取最新事项，保留草稿</Button>}
        <p role="status">{command.status}</p>
      </form>
      <section>
        <h3>已记录的进展</h3>
        {item.events?.length ? (
          item.events.map((event) => (
            <article className="profile-item" key={event.id}>
              <p className="meta">{shownTime(event.occurred_at)}</p>
              <p>{event.content}</p>
            </article>
          ))
        ) : (
          <p className="meta">尚无进展记录。</p>
        )}
      </section>
      <Feedback item={item} revision={version} refreshed={refresh} onSaved={onSaved} />
      <a className="button secondary" href={`#/chat?case=${encodeURIComponent(item.id)}`}>
        继续聊这件事
      </a>
      <a className="text-link quiet-link" href={`#/tarot?case=${encodeURIComponent(item.id)}`}>
        用塔罗梳理
      </a>
    </div>
  );
}
export default function Cases() {
  const query = useResource<Case[]>('/api/cases?subject_id=self');
  const refresh = () => {
    void query.refetch();
  };
  return (
    <div className="page" data-page="cases">
      <header className="page-heading row between">
        <h1>进行中的事</h1>
        <Panel
          sheet
          title="新建事项"
          description="先写具体的事项与目标，由你提交的内容会保存为原话。"
          trigger={<Button>新建事项</Button>}>
          <CreateCase onSaved={refresh} />
        </Panel>
      </header>
      <ResourceState loading={query.isPending} error={query.error} retry={refresh} />
      {query.data?.length === 0 && <p>还没有事项。可以在这里记下一个具体目标。</p>}
      {query.data?.map((item) => (
        <Panel
          sheet
          key={item.id}
          title={item.title}
          description="核对目标、修改事项或记录实际进展。"
          trigger={
            <button className="row-link full-row" type="button">
              <span className="case-body">
                <span className="row wrap">
                  <span className="case-title">{item.title}</span>
                  <Tag>{item.status === 'closed' ? '已关闭' : '进行中'}</Tag>
                </span>
                <span className="small-text secondary-text">{item.goal ?? item.state?.goal}</span>
              </span>
            </button>
          }>
          <CaseDetail item={item} onSaved={refresh} />
        </Panel>
      ))}
    </div>
  );
}
