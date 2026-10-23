import { useId, useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { Button, Input } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import type { EditIntent, OrganizeSnapshot } from './types';
import './review-tree.css';

export type ReviewEditorTarget =
  { kind: 'rename' | 'move_topic' | 'merge'; topic_id: string } | { kind: 'move_segment'; segment_id: string };

type Props = {
  target: ReviewEditorTarget | null;
  snapshot: OrganizeSnapshot;
  busy: boolean;
  onClose: () => void;
  onSubmit: (intent: EditIntent) => Promise<boolean>;
};
const headings = { rename: '修改话题名', move_topic: '移动话题', move_segment: '移动片段', merge: '合并话题' } as const;

function Editor({ target, snapshot, busy, onClose, onSubmit }: Props & { target: ReviewEditorTarget }) {
  const topicId =
    target.kind === 'move_segment'
      ? snapshot.segments.find(({ id }) => id === target.segment_id)?.topic_id
      : target.topic_id;
  const topic = snapshot.topics.find(({ id }) => id === topicId);
  const initialRevision = useRef(snapshot.revision);
  const returnFocus = useRef(document.activeElement instanceof HTMLElement ? document.activeElement : null);
  const submittingRef = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [title, setTitle] = useState(topic?.title ?? '');
  const [space, setSpace] = useState(topic?.space_id ?? snapshot.spaces[0]?.id ?? '');
  const mergeChoices = snapshot.topics.filter(
    (candidate) => candidate.id !== topicId && candidate.space_id === topic?.space_id,
  );
  const [destination, setDestination] = useState(
    target.kind === 'merge' ? (mergeChoices[0]?.id ?? '') : (topicId ?? ''),
  );
  const choices = snapshot.topics.filter(({ space_id }) => space_id === space);
  const changed = snapshot.revision !== initialRevision.current && !submitting;
  const locked = busy || submitting || changed || snapshot.status !== 'draft';
  const titleLength = Array.from(title.trim()).length;
  const inputId = useId();
  const errorId = useId();
  const topicChoices = target.kind === 'merge' ? mergeChoices : choices;
  const valid =
    Boolean(topic) &&
    (target.kind === 'rename'
      ? titleLength > 0 && titleLength <= 80 && title.trim() !== topic?.title
      : target.kind === 'move_topic'
        ? space !== topic?.space_id && snapshot.spaces.some(({ id }) => id === space)
        : topicChoices.some(({ id }) => id === destination) && destination !== topicId);
  const submit = async () => {
    if (locked || !valid || submittingRef.current) return;
    const intent: EditIntent =
      target.kind === 'move_segment'
        ? { kind: 'move_segment', segment_id: target.segment_id, target_topic_id: destination }
        : target.kind === 'rename'
          ? { kind: 'rename_topic', topic_id: target.topic_id, title: title.trim() }
          : target.kind === 'move_topic'
            ? { kind: 'move_topic', topic_id: target.topic_id, space_id: space }
            : { kind: 'merge_topics', topic_ids: [target.topic_id], target_topic_id: destination };
    submittingRef.current = true;
    setSubmitting(true);
    setError('');
    try {
      if (await onSubmit(intent)) onClose();
      else setError('草稿没有更新，请核对后再试。');
    } catch {
      setError('暂时没有保存成功，请稍后再试。');
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };
  const close = () => {
    if (!busy && !submittingRef.current) onClose();
  };
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content
          className="dialog sheet review-editor"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const previous = returnFocus.current;
            (previous?.isConnected && !previous.hasAttribute('disabled')
              ? previous
              : document.getElementById('review-title')
            )?.focus({
              preventScroll: true,
            });
          }}
          onEscapeKeyDown={(event) => {
            if (busy || submittingRef.current) event.preventDefault();
          }}
          onPointerDownOutside={(event) => {
            if (busy || submittingRef.current) event.preventDefault();
          }}>
          <Dialog.Title className="dialog-heading">{headings[target.kind]}</Dialog.Title>
          <Dialog.Description className="meta">只调整本批整理草稿，确认应用前不会改变原消息。</Dialog.Description>
          <Dialog.Close aria-label="关闭编辑" className="icon-button dialog-close" disabled={busy || submitting}>
            <X className="icon" aria-hidden="true" />
          </Dialog.Close>
          <form
            className="dialog-body review-editor-form"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}>
            <p className="small-text">当前话题：{topic?.title ?? '这个话题已不在当前草稿中'}</p>
            <fieldset disabled={locked || !topic} className="review-editor-fields">
              <legend className="sr-only">{headings[target.kind]}内容</legend>
              {target.kind === 'rename' ? (
                <div className="field">
                  <label htmlFor={inputId}>话题名</label>
                  <Input
                    id={inputId}
                    value={title}
                    maxLength={160}
                    autoComplete="off"
                    aria-describedby={`${inputId}-hint ${errorId}`}
                    aria-invalid={titleLength > 80 || undefined}
                    onChange={(event) => setTitle(event.target.value)}
                  />
                  <span id={`${inputId}-hint`} className="meta">
                    {titleLength}/80 字 · 不能为空
                  </span>
                </div>
              ) : (
                <>
                  {target.kind !== 'merge' && (
                    <div className="field">
                      <span>目标区</span>
                      <Select
                        label="目标区"
                        value={space}
                        options={snapshot.spaces.map(({ id, name }) => ({ value: id, label: name }))}
                        onChange={(value) => {
                          if (locked) return;
                          setSpace(value);
                          setDestination(snapshot.topics.find(({ space_id }) => space_id === value)?.id ?? '');
                        }}
                      />
                    </div>
                  )}
                  {target.kind !== 'move_topic' &&
                    (topicChoices.length ? (
                      <div className="field">
                        <span>{target.kind === 'merge' ? '并入哪个话题' : '目标话题'}</span>
                        <Select
                          label={target.kind === 'merge' ? '并入哪个话题' : '目标话题'}
                          value={destination}
                          options={topicChoices.map(({ id, title: text }) => ({ value: id, label: text }))}
                          onChange={(value) => {
                            if (!locked) setDestination(value);
                          }}
                        />
                      </div>
                    ) : (
                      <p className="meta">
                        {target.kind === 'merge'
                          ? '同区没有其他话题。请先把要合并的话题移到同一区。'
                          : '这个区暂时没有可接收的话题，请选其他区。'}
                      </p>
                    ))}
                </>
              )}
            </fieldset>
            {target.kind === 'move_segment' && (
              <p className="meta">移动只调整归属；待审片段仍需你接受，才会参加应用。</p>
            )}
            {target.kind === 'merge' && <p className="meta">合并后，两个话题的片段归入所选话题，原消息保持完整。</p>}
            {changed && (
              <p className="error-text" role="alert">
                草稿已变化，请关闭后重新核对。
              </p>
            )}
            <p id={errorId} className="error-text" role={error ? 'alert' : undefined}>
              {error}
            </p>
            <div className="review-editor-actions">
              <Button disabled={busy || submitting} onClick={close}>
                取消
              </Button>
              <Button type="submit" variant="primary" disabled={locked || !valid} loading={submitting}>
                保存到草稿
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function ReviewEditor(props: Props) {
  if (!props.target) return null;
  const key =
    props.target.kind === 'move_segment'
      ? `${props.target.kind}:${props.target.segment_id}`
      : `${props.target.kind}:${props.target.topic_id}`;
  return <Editor key={key} {...props} target={props.target} />;
}

export default ReviewEditor;
