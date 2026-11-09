import { useEffect, useRef, useState } from 'react';
import { ArrowUp, ImagePlus, Square, X } from 'lucide-react';
import { Button, IconButton } from '../components/ui/Controls';

export async function imagesFromFiles(files: File[], existing: string[] = []): Promise<string[]> {
  if (files.length + existing.length > 4) throw new Error('最多附 4 张图片');
  for (const file of files) {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('仅支持 JPEG、PNG、WebP 图片');
    if (file.size > 5 * 1024 * 1024) throw new Error('每张图片不能超过 5MB');
  }
  const added = await Promise.all(
    files.map(
      (file) =>
        new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result));
          reader.onerror = () => reject(new Error('图片没有读完整，请重新选择'));
          reader.readAsDataURL(file);
        }),
    ),
  );
  return [...existing, ...added];
}
export function LiveComposer({
  draft,
  setText,
  busy,
  images,
  setImages,
  send,
  stop,
  capabilities,
  submitting = false,
}: {
  draft: string;
  setText: (text: string) => void;
  busy: boolean;
  images: string[];
  setImages: (images: string[]) => void;
  send: () => void;
  stop: () => void;
  capabilities?: { queueWhileBusy?: boolean };
  submitting?: boolean;
}) {
  const picker = useRef<HTMLInputElement>(null),
    [error, setError] = useState('');
  const [reading, setReading] = useState(false);
  const composing = useRef(false);
  const imageRead = useRef({ epoch: 0, alive: true, images });
  imageRead.current.images = images;
  const queueEnabled = capabilities?.queueWhileBusy === true;
  const locked = busy && !queueEnabled;
  const access = useRef(locked);
  access.current = locked;
  const canSend = !locked && !reading && !submitting && Boolean(draft.trim());
  useEffect(() => {
    const context = imageRead.current;
    context.alive = true;
    return () => {
      context.alive = false;
      ++context.epoch;
    };
  }, []);
  useEffect(() => {
    ++imageRead.current.epoch;
    setReading(false);
  }, [images]);
  useEffect(() => {
    if (locked) {
      ++imageRead.current.epoch;
      setReading(false);
    }
  }, [locked]);
  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend && !composing.current) send();
      }}>
      {images.length > 0 && (
        <ul className="row wrap" aria-label="本轮附图">
          {images.map((image, index) => (
            <li key={index}>
              <span className="meta">附图 {index + 1}</span>
              <IconButton
                label={`移除附图${index + 1}`}
                disabled={locked}
                onClick={() => {
                  ++imageRead.current.epoch;
                  setReading(false);
                  setError('');
                  setImages(images.filter((_, item) => item !== index));
                }}>
                <X className="icon" />
              </IconButton>
              <details>
                <summary>预览附图 {index + 1}</summary>
                <img src={image} alt={`本轮附图${index + 1}`} />
              </details>
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="composer-row">
        <IconButton label="添加图片" disabled={locked || reading} onClick={() => picker.current?.click()}>
          <ImagePlus className="icon" />
        </IconButton>
        <input
          ref={picker}
          className="sr-only"
          aria-label="选择本轮图片"
          type="file"
          multiple
          accept="image/jpeg,image/png,image/webp"
          disabled={locked || reading}
          onChange={(event) => {
            const files = Array.from(event.target.files || []);
            event.target.value = '';
            if (!files.length || locked || reading) return;
            const context = imageRead.current;
            const epoch = ++context.epoch;
            const current = () =>
              context.alive && context.epoch === epoch && context.images === images && !access.current;
            setError('');
            setReading(true);
            void imagesFromFiles(files, images)
              .then((next) => {
                if (current()) setImages(next);
              })
              .catch((reason) => {
                if (current()) setError(reason instanceof Error ? reason.message : '图片没有读完整');
              })
              .finally(() => {
                if (current()) setReading(false);
              });
          }}
        />
        <textarea
          id="composer-input"
          rows={1}
          aria-label="和明镜说说"
          placeholder="和明镜说说…"
          value={draft}
          disabled={locked}
          onChange={(event) => setText(event.target.value)}
          onCompositionStart={() => {
            composing.current = true;
          }}
          onCompositionEnd={() => {
            composing.current = false;
          }}
          onFocus={(event) => event.target.scrollIntoView({ block: 'nearest' })}
          onKeyDown={(event) => {
            if (
              event.key === 'Enter' &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing &&
              event.nativeEvent.keyCode !== 229 &&
              !composing.current
            ) {
              event.preventDefault();
              if (canSend) send();
            }
          }}
        />
        {busy ? (
          <Button onClick={stop} aria-label="停止回答">
            <Square className="icon" />
            停止
          </Button>
        ) : null}
        {(!busy || queueEnabled) && (
          <button
            className="send-button"
            type="submit"
            aria-label={busy ? '排队发送' : '发送'}
            disabled={!canSend}
            aria-busy={submitting || undefined}>
            <ArrowUp className="icon" />
          </button>
        )}
      </div>
    </form>
  );
}
