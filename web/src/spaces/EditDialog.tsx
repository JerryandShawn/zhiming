import { useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { Button, Checkbox, Input } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { useSpacesDemo } from './store';

export type OrganizeEdit = { kind: 'space' | 'rename' | 'move' | 'merge' | 'split'; id: string };
const titles = { space: '改区名', rename: '改话题名', move: '移动话题', merge: '合并话题', split: '拆分话题' };

export default function EditDialog({ edit, close }: { edit: OrganizeEdit; close: () => void }) {
  const returnFocus = useRef(document.activeElement as HTMLElement | null);
  const state = useSpacesDemo();
  const topic = state.draft.topics.find((row) => row.id === edit.id);
  const space = state.draft.spaces.find((row) => row.id === edit.id);
  const available = state.draft.topics.filter(
    (row) => row.id !== edit.id && row.spaceId === topic?.spaceId && !state.draft.ignoredTopicIds.includes(row.id),
  );
  const [name, setName] = useState(
    edit.kind === 'space' ? (space?.name ?? '') : edit.kind === 'rename' ? (topic?.title ?? '') : '',
  );
  const [target, setTarget] = useState(edit.kind === 'move' ? (topic?.spaceId ?? '') : (available[0]?.id ?? ''));
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState('');
  const messages = state.data.messages.filter((row) => topic?.messageIds.includes(row.id));
  function save() {
    if (['space', 'rename', 'split'].includes(edit.kind) && (!name.trim() || name.trim().length > 60)) {
      setError('名称要有 1–60 个字；草稿还在，请核对后再试。');
      return;
    }
    let saved = false;
    if (edit.kind === 'space') saved = state.renameSpace(edit.id, name);
    if (edit.kind === 'rename') saved = state.renameTopic(edit.id, name);
    if (edit.kind === 'move') saved = state.moveTopic(edit.id, target);
    if (edit.kind === 'merge') saved = state.mergeTopics([edit.id], target);
    if (edit.kind === 'split') saved = state.splitTopic(edit.id, selected, name);
    if (saved) close();
    else setError(useSpacesDemo.getState().status);
  }
  return (
    <Dialog.Root open onOpenChange={(open) => !open && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content
          className="dialog organize-dialog"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const target = returnFocus.current;
            if (target?.isConnected) target.focus();
            else document.getElementById('organize-title')?.focus();
          }}>
          <Dialog.Title asChild>
            <h2 className="dialog-heading">{titles[edit.kind]}</h2>
          </Dialog.Title>
          <Dialog.Description className="small-text secondary-text">
            只编辑本页的整理草稿，点“应用整理”并确认后，才改变本地演示标签。原消息不会改写或删除。
          </Dialog.Description>
          <Dialog.Close className="icon-button dialog-close" aria-label="关闭编辑">
            <X className="icon" />
          </Dialog.Close>
          <form
            className="dialog-body stack"
            onSubmit={(event) => {
              event.preventDefault();
              save();
            }}>
            {['space', 'rename', 'split'].includes(edit.kind) && (
              <label className="field">
                {edit.kind === 'split' ? '新话题名称' : '名称'}
                <Input value={name} maxLength={60} onChange={(event) => setName(event.target.value)} />
              </label>
            )}
            {edit.kind === 'move' && (
              <Select
                label="移到哪个区"
                value={target}
                onChange={setTarget}
                options={state.draft.spaces
                  .filter((row) => !row.hidden)
                  .map((row) => ({ value: row.id, label: row.name }))}
              />
            )}
            {edit.kind === 'merge' && (
              <>
                <p>把“{topic?.title}”并入所选话题。两边的原消息都会保留。</p>
                {available.length ? (
                  <Select
                    label="并入哪个话题"
                    value={target}
                    onChange={setTarget}
                    options={available.map((row) => ({ value: row.id, label: row.title }))}
                  />
                ) : (
                  <p>同区暂无可合并的话题。可以先移动到同一区。</p>
                )}
              </>
            )}
            {edit.kind === 'split' && (
              <fieldset className="organize-message-picker stack">
                <legend>选入新话题的消息</legend>
                <p className="meta">至少选择一条，并给原话题留下一条。可同时选中一问一答。</p>
                {messages.map((message) => (
                  <label className="organize-message-option" key={message.id}>
                    <Checkbox
                      label={`选择消息：${message.text}`}
                      checked={selected.includes(message.id)}
                      onChange={(event) => {
                        setSelected(
                          event.target.checked ? [...selected, message.id] : selected.filter((id) => id !== message.id),
                        );
                      }}
                    />
                    <span>
                      <span className="meta">
                        {message.role === 'user' ? '你' : '明镜'} ·{' '}
                        {new Date(message.at).toLocaleString('zh-CN', { timeZone: 'Asia/Taipei' })}
                      </span>
                      <br />
                      {message.text}
                    </span>
                  </label>
                ))}
              </fieldset>
            )}
            {error && <p role="alert">{error}</p>}
            <div className="row wrap">
              <Button type="submit" variant="primary" disabled={edit.kind === 'merge' && !available.length}>
                保存到草稿
              </Button>
              <Button onClick={close}>取消</Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
