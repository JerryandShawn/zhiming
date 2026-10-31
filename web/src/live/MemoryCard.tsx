import { useState } from 'react';
import { api } from '../api/client';
import { pendingPayload } from '../api/operations';
import { Button, Checkbox, Input, Tag, Textarea } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { record, rows, text, useCommand } from './common';
import type { Fact } from './types';

export function memoryPayload(fact: Fact, nextText: string, rawValue: string, consent: boolean, revision: number) {
  const corrected = nextText.trim();
  if (!corrected) throw new Error('请写下更正后的内容。');
  const payload: Record<string, unknown> = { text: corrected, expected_revision: revision };
  if (fact.field) {
    if (!consent) throw new Error('请核对结构化资料并勾选更新授权。');
    if (!rawValue.trim() || !corrected.includes(rawValue.trim())) throw new Error('更正原话中必须写明新的资料值。');
    const value =
      typeof fact.value === 'number'
        ? Number(rawValue)
        : typeof fact.value === 'boolean'
          ? rawValue === 'True'
          : rawValue.trim();
    if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('资料值需要有效数值。');
    if (typeof fact.value === 'boolean' && !['True', 'False'].includes(rawValue))
      throw new Error('布尔资料值必须为 True 或 False。');
    payload.value = value;
  }
  return payload;
}
function Provenance({ fact }: { fact: Fact }) {
  const [source, setSource] = useState<Record<string, unknown> | null>(null);
  const [audit, setAudit] = useState<Record<string, unknown>[] | null>(null);
  const [error, setError] = useState('');
  async function load(kind: 'source' | 'audit') {
    try {
      const result = await api<unknown>(`/api/memories/${encodeURIComponent(fact.id)}/${kind}`);
      if (kind === 'source') setSource(record(result));
      else setAudit(rows(result));
      setError('');
    } catch {
      setError('来源或修改记录读取未完成，请重试。');
    }
  }
  return (
    <details className="disclosure">
      <summary>来源与修改记录</summary>
      <div className="disclosure-content stack">
        <Button onClick={() => void load('source')}>查看原始来源</Button>
        {source &&
          (source.source_available === true ? (
            <>
              {fact.source_refs
                ?.filter((ref) => typeof ref.quote === 'string')
                .map((ref, index) => (
                  <blockquote key={index}>{ref.quote}</blockquote>
                ))}
              {!fact.source_refs?.some((ref) => typeof ref.quote === 'string') && (
                <p>来源仍保留，但此条未提供可展示的授权节选。</p>
              )}
            </>
          ) : (
            <p>原始来源已不可用。</p>
          ))}
        <Button onClick={() => void load('audit')}>查看修改记录</Button>
        {audit?.map((item, index) => (
          <p key={index}>
            状态：{text(item.operation)} · 版本 {text(item.revision)} · {text(item.at)}
          </p>
        ))}
        {error && <p role="alert">{error}</p>}
      </div>
    </details>
  );
}
export default function MemoryCard({ fact, onSaved }: { fact: Fact; onSaved: () => void }) {
  const editScope = `memory-edit:${fact.id}`;
  const pending = pendingPayload<Record<string, unknown>>(editScope);
  const [content, setContent] = useState(String(pending?.text ?? fact.text ?? fact.content ?? ''));
  const [value, setValue] = useState(() => (pending?.value !== undefined ? String(pending.value) : ''));
  const [consent, setConsent] = useState(Boolean(pending && fact.field));
  const stopPending = pendingPayload<Record<string, unknown>>(`memory-stop:${fact.id}`);
  const deletePending = pendingPayload<Record<string, unknown>>(`memory-delete:${fact.id}`);
  const [version, setVersion] = useState(
    Number(
      pending?.expected_revision ?? stopPending?.expected_revision ?? deletePending?.expected_revision ?? fact.revision,
    ),
  );
  const [scope, setScope] = useState(() =>
    String(pendingPayload<Record<string, unknown>>(`memory-delete:${fact.id}`)?.scope ?? 'fact'),
  );
  const [confirmed, setConfirmed] = useState(Boolean(deletePending));
  const edit = useCommand(editScope),
    stop = useCommand(`memory-stop:${fact.id}`),
    deletion = useCommand(`memory-delete:${fact.id}`);
  const privateField = fact.field?.startsWith('birth.') || fact.kind === 'profile';
  const busy = edit.busy || stop.busy || deletion.busy;
  const conflict = edit.conflict || stop.conflict || deletion.conflict;
  const active = fact.status === 'active';
  async function save() {
    try {
      const payload = memoryPayload(fact, content, value, consent, version);
      const result = await edit.submit<Fact>(
        'PATCH',
        `/api/memories/${encodeURIComponent(fact.id)}`,
        payload,
        (item) => Boolean(item.id) && Number.isInteger(item.revision) && item.write_status === 'saved',
      );
      if (result) {
        edit.setStatus('记忆更正已保存。');
        onSaved();
      }
    } catch (error) {
      edit.setStatus(error instanceof Error ? error.message : '请核对更正内容。');
    }
  }
  async function retire(remove: boolean) {
    const command = remove ? deletion : stop;
    const path = `/api/memories/${encodeURIComponent(fact.id)}`;
    const payload = remove ? { expected_revision: version, scope } : { expected_revision: version, status: 'hidden' };
    const result = await command.submit<Fact>(
      remove ? 'DELETE' : 'PATCH',
      remove ? `${path}?scope=${scope}&expected_revision=${version}` : path,
      payload,
      (item) =>
        item.id === fact.id &&
        item.write_status === (remove ? 'deleted' : 'stopped') &&
        Number.isInteger(item.revision),
    );
    if (result) {
      command.setStatus(remove ? '已收到删除回执。' : '已收到停用回执。');
      onSaved();
    }
  }
  async function refresh() {
    try {
      const facts = await api<Fact[]>('/api/memories?subject_id=self');
      const latest = facts.find((item) => item.id === fact.id);
      if (!latest || latest.status !== 'active') {
        edit.setStatus('这条记忆已不再有效，请返回列表核对。');
        onSaved();
        return;
      }
      setVersion(latest.revision);
      edit.unlock();
      stop.unlock();
      deletion.unlock();
    } catch {
      edit.setStatus('最新记忆读取失败，草稿仍保留。');
    }
  }
  return (
    <article className="profile-item stack" aria-label="记忆条目">
      <div className="row between">
        <Tag>{fact.category ?? fact.kind ?? '个人记录'}</Tag>
        <span className="meta">{active ? '正在使用' : '已停用或已更正'}</span>
      </div>
      {privateField ? (
        <p>
          出生资料已隐藏。
          <a className="text-link quiet-link" href="#/me?section=profile">
            到资料确认页核对
          </a>
        </p>
      ) : (
        <>
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}>
            <fieldset className="stack" disabled={busy || !active || Boolean(pending)}>
              <label className="field">
                记忆内容
                <Textarea maxLength={2000} value={content} onChange={(event) => setContent(event.target.value)} />
              </label>
              {fact.field && (
                <>
                  <label className="field">
                    更正后的资料值
                    <Input value={value} onChange={(event) => setValue(event.target.value)} />
                  </label>
                  <p className="meta">新值也须出现在更正原话中。布尔值使用 True 或 False。</p>
                  <label className="row">
                    <Checkbox
                      label="确认结构化资料并授权更新"
                      checked={consent}
                      onChange={(event) => setConsent(event.target.checked)}
                    />
                    我确认这项资料并授权更新。
                  </label>
                </>
              )}
            </fieldset>
            <Button type="submit" disabled={busy || !active || conflict}>
              {pending ? '重试原记忆更正' : '保存记忆更正'}
            </Button>
          </form>
          <Provenance fact={fact} />
        </>
      )}
      {active && (
        <Button
          disabled={busy || conflict || Boolean(pending) || Boolean(deletePending)}
          onClick={() => void retire(false)}>
          停用这条记忆
        </Button>
      )}
      <details className="disclosure">
        <summary>删除范围</summary>
        <div className="disclosure-content stack">
          <fieldset disabled={busy || Boolean(pendingPayload(`memory-delete:${fact.id}`))} className="stack">
            <Select
              label="删除范围"
              value={scope}
              onChange={setScope}
              options={[
                { value: 'fact', label: '只忘记这条事实，保留原始聊天' },
                { value: 'source', label: '删除整段来源及关联内容' },
              ]}
            />
            <label className="row">
              <Checkbox
                label="确认删除所选范围"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              我已核对删除范围。
            </label>
          </fieldset>
          <p className="meta">删除来源会影响关联记录。已经投递到其他渠道的消息无法撤回。</p>
          <Button
            variant="destructive"
            disabled={!confirmed || busy || conflict || Boolean(pending) || Boolean(stopPending)}
            onClick={() => void retire(true)}>
            确认删除所选范围
          </Button>
        </div>
      </details>
      {conflict && <Button onClick={() => void refresh()}>读取最新记忆，保留草稿</Button>}
      <p role="status">{edit.status}</p>
      <p role="status">{stop.status}</p>
      <p role="status">{deletion.status}</p>
    </article>
  );
}
