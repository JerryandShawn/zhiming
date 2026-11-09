export type Frame = { id: string; event: string; data: string };

// A persistent decoder handles CRLF and UTF-8 characters split across reads.
export async function readSse(
  response: Response,
  accept: (frame: Frame) => unknown,
  signal?: AbortSignal,
  onHeartbeat?: () => void,
) {
  if (!response.body) throw new Error('服务器没有返回事件流');
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let buffer = '',
    event = '',
    id = '',
    data: string[] = [];
  async function line(value: string) {
    signal?.throwIfAborted();
    if (value === '') {
      if (data.length) await accept({ id, event, data: data.join('\n') });
      event = '';
      data = [];
      return;
    }
    if (value.startsWith(':')) {
      // Frozen-v1 heartbeats are comments: they never create a frame or move its id.
      if (value.slice(1).trim() === 'ping') onHeartbeat?.();
      return;
    }
    const split = value.indexOf(':'),
      field = split < 0 ? value : value.slice(0, split);
    let content = split < 0 ? '' : value.slice(split + 1);
    if (content.startsWith(' ')) content = content.slice(1);
    if (field === 'id' && !content.includes('\0')) id = content;
    if (field === 'event') event = content;
    if (field === 'data') data.push(content);
  }
  const abort = () => {
    void reader.cancel(signal?.reason).catch(() => undefined);
  };
  signal?.addEventListener('abort', abort, { once: true });
  try {
    while (true) {
      signal?.throwIfAborted();
      const chunk = await reader.read();
      signal?.throwIfAborted();
      buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      let position: number;
      while ((position = buffer.search(/[\r\n]/)) >= 0) {
        // A final CR may be the first half of CRLF in the next read.
        if (!chunk.done && buffer[position] === '\r' && position === buffer.length - 1) break;
        const width = buffer[position] === '\r' && buffer[position + 1] === '\n' ? 2 : 1;
        await line(buffer.slice(0, position));
        buffer = buffer.slice(position + width);
      }
      if (chunk.done) break;
    }
    // Incomplete frames are intentionally not committed on disconnect.
  } finally {
    signal?.removeEventListener('abort', abort);
    // A transport's asynchronous cancellation must not keep an aborted UI waiting.
    void reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
