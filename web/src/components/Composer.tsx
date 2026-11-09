import { useState } from 'react';
import { ArrowUp, EyeOff, ImagePlus, Square, X } from 'lucide-react';
import { IconButton, Tag } from './ui/Controls';
import { useUi } from '../state';

export function Composer({ busy = false, subdued = false }: { busy?: boolean; subdued?: boolean }) {
  const [text, setText] = useState('');
  const [context, setContext] = useState(true);
  const notify = useUi((value) => value.notify);
  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        notify('静态预览不会发送消息。');
      }}>
      <div className="row">
        {context && (
          <button className="context-chip" type="button" aria-label="移除事项跳槽" onClick={() => setContext(false)}>
            <Tag>
              跳槽
              <X className="icon small" />
            </Tag>
          </button>
        )}
        <span className="meta row">
          <EyeOff className="icon small" />
          只在这里聊
        </span>
      </div>
      <div className="composer-row">
        <IconButton label="添加图片" onClick={() => notify('图片上传在后续接入。')}>
          <ImagePlus className="icon" />
        </IconButton>
        <textarea
          id="composer-input"
          rows={1}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="和明镜说说…"
          aria-label="和明镜说说"
        />
        <button
          className={`send-button ${busy || subdued ? 'stopping' : ''}`}
          type="submit"
          aria-label={busy ? '停止回答' : '发送'}>
          {busy ? <Square className="icon" /> : <ArrowUp className="icon" />}
        </button>
      </div>
    </form>
  );
}
