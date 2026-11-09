import { useState } from 'react';
import { Button, Input, Segmented, Switch, Tag } from '../../components/ui/Controls';
import type { ContactDraft, ContactSettings, SettingsPort } from './types';
import { useSettingsCommand } from './useSettingsCommand';

export function ContactForm({ item, port }: { item: ContactSettings; port: SettingsPort }) {
  const [draft, setDraft] = useState<ContactDraft>(() => ({
    ...item,
    disabledCategories: [...item.disabledCategories],
  }));
  const [revision, setRevision] = useState(item.revision),
    [review, setReview] = useState(false);
  const operation = useSettingsCommand(port),
    locked = operation.busy || operation.hasPending;
  return (
    <section className="setting-group" aria-label="主动联系">
      <h2>主动联系</h2>
      <p className="meta">免打扰和每日上限只约束跟进，不会改变你指定的晨报时间。</p>
      <form
        className="stack small"
        onSubmit={(event) => {
          event.preventDefault();
          void operation
            .run(
              {
                type: 'contact-save',
                expectedRevision: revision,
                requestId: crypto.randomUUID(),
                draft: { ...draft, disabledCategories: [...draft.disabledCategories] },
              },
              (receipt, command) =>
                command.type === 'contact-save' &&
                receipt.write_status === 'saved' &&
                receipt.contact?.followup === command.draft.followup &&
                receipt.contact.dailyCap === command.draft.dailyCap &&
                receipt.contact.dndStart === command.draft.dndStart &&
                receipt.contact.dndEnd === command.draft.dndEnd &&
                JSON.stringify(receipt.contact.disabledCategories) === JSON.stringify(command.draft.disabledCategories),
            )
            .then((receipt) => {
              if (receipt?.contact) {
                setRevision(receipt.contact.revision);
                setDraft({ ...receipt.contact, disabledCategories: [...receipt.contact.disabledCategories] });
              }
            });
        }}>
        <fieldset disabled={locked} className="stack small">
          <div className="setting-row">
            <span>事情有进展时问问我</span>
            <Switch
              label="跟进开关"
              checked={draft.followup}
              disabled={locked}
              onChange={(followup) => setDraft((old) => ({ ...old, followup }))}
            />
          </div>
          <Segmented
            label="每天最多联系次数"
            value={String(draft.dailyCap)}
            options={['1', '2', '3'].map((value) => ({ value, label: `${value}次` }))}
            onChange={(value) => setDraft((old) => ({ ...old, dailyCap: Number(value) as 1 | 2 | 3 }))}
          />
          <div className="settings-contact-times">
            {(
              [
                ['dndStart', '免打扰开始时间'],
                ['dndEnd', '免打扰结束时间'],
              ] as const
            ).map(([key, label]) => (
              <label className="field" key={key}>
                {label}
                <Input
                  type="time"
                  aria-label={label}
                  value={draft[key]}
                  onChange={(event) => setDraft((old) => ({ ...old, [key]: event.target.value }))}
                />
              </label>
            ))}
          </div>
        </fieldset>
        <p className="meta">已关闭的提醒类别</p>
        <div className="row wrap">
          {item.disabledCategories.length ? (
            item.disabledCategories.map((category) => (
              <Tag key={category}>
                {({ health: '健康', finance: '财务', relationship: '关系' } as Record<string, string>)[category] ||
                  '其他类别'}
              </Tag>
            ))
          ) : (
            <span className="meta">暂无</span>
          )}
        </div>
        {operation.error && <p role="alert">{operation.error}</p>}
        {operation.saved && (
          <p role="status" className="settings-feedback">
            已保存主动联系设置（本地演示）。
          </p>
        )}
        {operation.conflict && (
          <div className="stack small">
            <Button onClick={() => setReview(true)}>读取当前主动联系设置</Button>
            {review && (
              <div className="settings-preview">
                <p>
                  {item.followup ? '跟进开启' : '跟进关闭'} · 每日 {item.dailyCap} 次 · {item.dndStart} 至 {item.dndEnd}
                </p>
                <Button
                  onClick={() => {
                    setRevision(item.revision);
                    operation.reset();
                    setReview(false);
                  }}>
                  已核对，保留草稿继续
                </Button>
              </div>
            )}
          </div>
        )}
        <Button type="submit" disabled={operation.conflict} loading={operation.busy}>
          {operation.hasPending ? '重试原主动联系设置' : '保存主动联系设置'}
        </Button>
      </form>
    </section>
  );
}
