import { useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { ChevronDown, Lock, X } from 'lucide-react';
import { Button, Input, Tag } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { useSpacesDemo } from './store';

interface RouteBadgeProps {
  spaceId: string;
  topicId: string;
  messageId?: string;
  prefix?: string;
  secondarySpaceId?: string;
  onChange?: (spaceId: string, topicId: string) => void;
}

export function RouteBadge({
  spaceId,
  topicId,
  messageId,
  secondarySpaceId,
  onChange,
  prefix = '归入',
}: RouteBadgeProps) {
  const data = useSpacesDemo((state) => state.data);
  const routeMessage = useSpacesDemo((state) => state.routeMessage);
  const [open, setOpen] = useState(false);
  const [chosenSpace, setSpace] = useState(spaceId);
  const [chosenTopic, setTopic] = useState(topicId);
  const [title, setTitle] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const trigger = useRef<HTMLButtonElement>(null);
  const space = data.spaces.find((item) => item.id === spaceId);
  const topic = data.topics.find((item) => item.id === topicId);
  const secondary = data.spaces.find((item) => item.id === secondarySpaceId);
  const topics = data.topics.filter((item) => item.spaceId === chosenSpace);
  const canCreate = Boolean(messageId);
  const openEditor = (next: boolean) => {
    if (next) {
      setSpace(spaceId);
      setTopic(topicId);
      setTitle('');
      setError('');
    }
    setOpen(next);
  };
  const submit = () => {
    if (!chosenTopic || (chosenTopic === 'new' && !title.trim())) {
      setError('新话题需要一个名字。');
      return;
    }
    if (messageId) {
      if (!routeMessage(messageId, chosenSpace, chosenTopic, title.trim())) {
        setError(useSpacesDemo.getState().status || '这条示例还没有改好，可以关闭后重试。');
        return;
      }
      setNotice('本地模拟已改归属；原文未改，刷新后重置。');
    } else {
      onChange?.(chosenSpace, chosenTopic);
      setNotice('已更改本地输入归属，尚未发送。');
    }
    setOpen(false);
  };
  return (
    <div className="spaces-route">
      <Dialog.Root open={open} onOpenChange={openEditor}>
        <Dialog.Trigger asChild>
          <button ref={trigger} type="button" className="spaces-route-trigger">
            <Tag tone="neutral">
              {space?.sensitive && <Lock className="icon small" role="img" aria-label="敏感区" />}
              {prefix}：{space?.name || '日常'} · {topic?.title || '尚未选择话题'}
              <ChevronDown className="icon small" aria-hidden="true" />
            </Tag>
          </button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="overlay" />
          <Dialog.Content
            className="dialog spaces-route-dialog"
            onCloseAutoFocus={(event) => {
              if (!trigger.current?.isConnected) {
                event.preventDefault();
                document.querySelector<HTMLElement>('.spaces-conversation-heading h2')?.focus();
              }
            }}>
            <Dialog.Title className="dialog-heading">更改归区</Dialog.Title>
            <Dialog.Description className="small-text secondary-text">
              {messageId ? '仅调整此条回答的本地归属，不会连带移动其他消息。' : '仅调整下一条输入的本地归属。'}
              原文不会改动，刷新后重置。
            </Dialog.Description>
            <Dialog.Close className="icon-button dialog-close" aria-label="关闭归区编辑">
              <X className="icon" />
            </Dialog.Close>
            <div className="dialog-body stack">
              <div className="field">
                主区
                <Select
                  label="主区"
                  value={chosenSpace}
                  options={data.spaces
                    .filter((item) => !item.hidden)
                    .map((item) => ({ value: item.id, label: `${item.name}${item.sensitive ? '（敏感区）' : ''}` }))}
                  onChange={(value) => {
                    setSpace(value);
                    setTopic(data.topics.find((item) => item.spaceId === value)?.id || (canCreate ? 'new' : ''));
                    setError('');
                  }}
                />
              </div>
              <div className="field">
                话题
                <Select
                  label="归入话题"
                  value={chosenTopic}
                  options={[
                    ...topics.map((item) => ({ value: item.id, label: item.title })),
                    ...(canCreate ? [{ value: 'new', label: '新建话题…' }] : []),
                    ...(!topics.length && !canCreate ? [{ value: '', label: '这个区还没有话题' }] : []),
                  ]}
                  onChange={(value) => {
                    setTopic(value);
                    setError('');
                  }}
                />
              </div>
              {chosenTopic === 'new' && (
                <label className="field">
                  新话题名字
                  <Input value={title} maxLength={60} onChange={(event) => setTitle(event.target.value)} />
                </label>
              )}
              {error && <p role="alert">{error}</p>}
              <div className="row wrap">
                <Button variant="primary" onClick={submit}>
                  确认本地归属
                </Button>
                <Dialog.Close asChild>
                  <Button>取消</Button>
                </Dialog.Close>
              </div>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      {secondary && <span className="meta">也涉及：{secondary.name}</span>}
      {notice && (
        <p className="meta" role="status">
          {notice}
        </p>
      )}
    </div>
  );
}
