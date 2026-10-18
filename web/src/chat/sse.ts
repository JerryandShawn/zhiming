export type Frame = { id: string; event: string; data: string };

// A persistent decoder handles CRLF and UTF-8 characters split across reads.
export async function readSse(response: Response, accept: (frame: Frame) => void, signal?: AbortSignal) {
  if (!response.body) throw new Error('服务器没有返回事件流');
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let buffer = '',
    event = '',
    id = '',
    data: string[] = [];
  function line(value: string) {
    if (value === '') {
      if (data.length) accept({ id, event, data: data.join('\n') });
      event = '';
      data = [];
      return;
    }
    if (value.startsWith(':')) return;
    const split = value.indexOf(':'),
      field = split < 0 ? value : value.slice(0, split);
    let content = split < 0 ? '' : value.slice(split + 1);
    if (content.startsWith(' ')) content = content.slice(1);
    if (field === 'id' && !content.includes('\0')) id = content;
    if (field === 'event') event = content;
    if (field === 'data') data.push(content);
  }
  try {
    while (true) {
      signal?.throwIfAborted();
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      let position: number;
      while ((position = buffer.search(/[\r\n]/)) >= 0) {
        // A final CR may be the first half of CRLF in the next read.
        if (!chunk.done && buffer[position] === '\r' && position === buffer.length - 1) break;
        const width = buffer[position] === '\r' && buffer[position + 1] === '\n' ? 2 : 1;
        line(buffer.slice(0, position));
        buffer = buffer.slice(position + width);
      }
      if (chunk.done) break;
    }
    // Incomplete frames are intentionally not committed on disconnect.
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
