import { useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { Button, Tag } from '../components/ui/Controls';
import EditDialog, { type OrganizeEdit } from './EditDialog';
import ProposalTree from './ProposalTree';
import { useSpacesDemo } from './store';
import './organize.css';

export default function OrganizePage() {
  const { data, draft, applied, status, apply, revert, resetDraft } = useSpacesDemo();
  const [edit, setEdit] = useState<OrganizeEdit | null>(null);
  const [confirm, setConfirm] = useState<'apply' | 'revert' | null>(null);
  const [confirmError, setConfirmError] = useState('');
  const returnFocus = useRef<HTMLElement | null>(null);
  const ignored = draft.topics.filter((topic) => draft.ignoredTopicIds.includes(topic.id));
  function commit() {
    const result = confirm === 'apply' ? apply() : revert();
    if (result) setConfirm(null);
    else setConfirmError(useSpacesDemo.getState().status);
  }
  function openConfirm(kind: 'apply' | 'revert') {
    returnFocus.current = document.activeElement as HTMLElement | null;
    setConfirmError('');
    setConfirm(kind);
  }
  return (
    <section className="page organize-page stack" aria-labelledby="organize-title" data-page="organize">
      <header className="stack small">
        <h1 id="organize-title" tabIndex={-1}>
          整理建议
        </h1>
        <p>先核对区与话题，再应用整理。原消息一条不改，一条不少。</p>
      </header>
      <div className="organize-demo-note stack small">
        <div>
          <Tag>合成数据 · 本地模拟</Tag>
        </div>
        <p className="small-text">
          这里只演示整理过程，不能整理真实旧聊天。编辑先保存在草稿；应用只改变本地演示标签，刷新后重置。没有模型请求。
        </p>
        <p className="meta">
          原消息共 {data.messages.length} 条 · 草稿 {draft.topics.length - ignored.length} 个话题 · 本批忽略{' '}
          {ignored.length} 个话题
        </p>
      </div>
      <div className="row wrap organize-actions">
        <Button variant="primary" disabled={Boolean(applied)} onClick={() => openConfirm('apply')}>
          应用整理
        </Button>
        <Button disabled={!applied} onClick={() => openConfirm('revert')}>
          撤销本批整理
        </Button>
        <Button variant="ghost" disabled={Boolean(applied)} onClick={resetDraft}>
          重置草稿
        </Button>
      </div>
      {applied && (
        <p className="small-text">
          当前演示批次：<code>{applied.batchId}</code>。已应用，仅保存在本页；可撤销后继续编辑。
        </p>
      )}
      {status && (
        <p className="small-text" role="status">
          {status}
        </p>
      )}
      <ProposalTree onEdit={setEdit} />
      {Boolean(ignored.length) && (
        <section className="stack small" aria-label="本批忽略的话题">
          <h2>本批忽略</h2>
          <p className="small-text">这些话题不参加本批整理，原消息仍保留。应用前可重置草稿，把它们放回来。</p>
          <ul>
            {ignored.map((topic) => (
              <li key={topic.id}>
                {topic.title} · {topic.messageIds.length} 条消息仍保留
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="stack small">
        <Button disabled>让明镜帮我起标题</Button>
        <p className="meta">标题生成功能尚未接入，本页不会发送模型请求。你现在可以直接改名。</p>
      </section>
      {edit && <EditDialog edit={edit} close={() => setEdit(null)} />}
      <Dialog.Root open={Boolean(confirm)} onOpenChange={(open) => !open && setConfirm(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="overlay" />
          <Dialog.Content
            className="dialog organize-dialog"
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              const target = returnFocus.current;
              if (target?.isConnected && !target.hasAttribute('disabled')) target.focus();
              else document.querySelector<HTMLButtonElement>('.organize-actions button:not(:disabled)')?.focus();
            }}>
            <Dialog.Title asChild>
              <h2 className="dialog-heading">{confirm === 'apply' ? '应用这批演示整理？' : '撤销这批演示整理？'}</h2>
            </Dialog.Title>
            <Dialog.Description className="small-text secondary-text">
              {confirm === 'apply'
                ? '只将当前草稿应用到合成数据的区与话题标签；忽略项仍保留原消息。不会写入服务器，刷新即重置。'
                : '恢复应用前的本地演示标签。原消息保持完整，不会删除任何对话。'}
            </Dialog.Description>
            <Dialog.Close className="icon-button dialog-close" aria-label="关闭确认">
              <X className="icon" />
            </Dialog.Close>
            <div className="dialog-body stack">
              {confirm === 'revert' && <p className="meta">演示批次：{applied?.batchId}</p>}
              {confirmError && <p role="alert">{confirmError}</p>}
              <div className="row wrap">
                <Button variant="primary" onClick={commit}>
                  {confirm === 'apply' ? '确认应用演示整理' : '确认撤销演示整理'}
                </Button>
                <Button onClick={() => setConfirm(null)}>取消</Button>
              </div>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
