import { useState, type ComponentProps } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LiveComposer } from '../src/chat/Composer';
import QueueList from '../src/night/queue/QueueList';
import type { QueueItem } from '../src/night/queue/types';

const oldImage = 'data:image/png;base64,b2xk';
const newImage = 'data:image/png;base64,bmV3';
const imageFile = () => new File(['synthetic'], 'synthetic.png', { type: 'image/png' });
const input = () => screen.getByRole('textbox', { name: '和明镜说说' });
const picker = () => screen.getByLabelText('选择本轮图片', { exact: true });
type Captured = { draft: string; images: string[] };
function Harness({
  busy = false,
  queue = false,
  submitting = false,
  initialImages = [],
  onSend,
  onStop,
}: {
  busy?: boolean;
  queue?: boolean;
  submitting?: boolean;
  initialImages?: string[];
  onSend?: (value: Captured) => void;
  onStop?: () => void;
}) {
  const [draft, setText] = useState('继续说的合成消息');
  const [images, setImages] = useState(initialImages);
  return (
    <LiveComposer
      {...{ busy, submitting, draft, setText, images, setImages }}
      capabilities={{ queueWhileBusy: queue }}
      send={() => onSend?.({ draft, images })}
      stop={() => onStop?.()}
    />
  );
}
function deferredImages() {
  const readers: DeferredReader[] = [];
  class DeferredReader {
    result = newImage;
    onload?: () => void;
    onerror?: () => void;
    readAsDataURL() {
      readers.push(this);
    }
  }
  vi.stubGlobal('FileReader', DeferredReader);
  return readers;
}
afterEach(() => vi.unstubAllGlobals());

describe('explicit busy composer queue capability', () => {
  it.each([undefined, { queueWhileBusy: false }])(
    'keeps legacy busy editing and sending disabled: %j',
    async (capabilities) => {
      const stop = vi.fn(),
        send = vi.fn();
      render(
        <LiveComposer
          draft="旧接口合成草稿"
          busy
          images={[oldImage]}
          setText={vi.fn()}
          setImages={vi.fn()}
          send={send}
          stop={stop}
          capabilities={capabilities}
        />,
      );
      expect(input()).toBeDisabled();
      expect(picker()).toBeDisabled();
      expect(screen.getByRole('button', { name: '添加图片' })).toBeDisabled();
      expect(screen.getByRole('button', { name: '移除附图1' })).toBeDisabled();
      expect(screen.queryByRole('button', { name: '发送' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: '排队发送' })).not.toBeInTheDocument();
      fireEvent.submit(input().closest('form')!);
      expect(send).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole('button', { name: '停止回答' }));
      expect(stop).toHaveBeenCalledOnce();
    },
  );

  it('allows editing, removing attachments, stopping and queueing together only when enabled', async () => {
    const send = vi.fn(),
      stop = vi.fn();
    render(<Harness busy queue initialImages={[oldImage]} onSend={send} onStop={stop} />);
    expect(input()).toBeEnabled();
    expect(picker()).toBeEnabled();
    await userEvent.clear(input());
    await userEvent.type(input(), '这段说完再聊的合成补充');
    await userEvent.click(screen.getByRole('button', { name: '移除附图1' }));
    await userEvent.click(screen.getByRole('button', { name: '排队发送' }));
    expect(send).toHaveBeenCalledWith({ draft: '这段说完再聊的合成补充', images: [] });
    await userEvent.click(screen.getByRole('button', { name: '停止回答' }));
    expect(stop).toHaveBeenCalledOnce();
  });

  it.each([false, true])('pending submission blocks sends but preserves editing: busy=%s', async (busy) => {
    const send = vi.fn();
    render(<Harness queue busy={busy} submitting initialImages={[oldImage]} onSend={send} />);
    expect(input()).toBeEnabled();
    expect(picker()).toBeEnabled();
    expect(screen.getByRole('button', { name: busy ? '排队发送' : '发送' })).toBeDisabled();
    fireEvent.change(input(), { target: { value: '提交中继续写的合成草稿' } });
    expect(input()).toHaveValue('提交中继续写的合成草稿');
    fireEvent.keyDown(input(), { key: 'Enter' });
    fireEvent.submit(input().closest('form')!);
    expect(send).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '移除附图1' }));
    expect(screen.queryByRole('list', { name: '本轮附图' })).not.toBeInTheDocument();
    if (busy) expect(screen.getByRole('button', { name: '停止回答' })).toBeEnabled();
  });

  it('uses one send guard for Enter, IME composition, Shift+Enter and form submission', () => {
    const send = vi.fn();
    render(<Harness busy queue onSend={send} />);
    fireEvent.keyDown(input(), { key: 'Enter', isComposing: true });
    fireEvent.keyDown(input(), { key: 'Enter', keyCode: 229 });
    fireEvent.compositionStart(input());
    fireEvent.keyDown(input(), { key: 'Enter' });
    fireEvent.submit(input().closest('form')!);
    fireEvent.compositionEnd(input());
    fireEvent.keyDown(input(), { key: 'Enter', shiftKey: true });
    expect(send).not.toHaveBeenCalled();
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(send).toHaveBeenCalledOnce();
    fireEvent.change(input(), { target: { value: '   ' } });
    fireEvent.submit(input().closest('form')!);
    expect(send).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: '排队发送' })).toBeDisabled();
  });

  it('blocks Enter and submit during image reading while text remains editable', async () => {
    const readers = deferredImages(),
      send = vi.fn();
    render(<Harness busy queue onSend={send} />);
    fireEvent.change(picker(), { target: { files: [imageFile()] } });
    expect(readers).toHaveLength(1);
    expect(input()).toBeEnabled();
    expect(screen.getByRole('button', { name: '排队发送' })).toBeDisabled();
    fireEvent.keyDown(input(), { key: 'Enter' });
    fireEvent.submit(input().closest('form')!);
    expect(send).not.toHaveBeenCalled();
    fireEvent.change(input(), { target: { value: '附图读入期间继续写' } });
    await act(async () => {
      readers[0].onload?.();
    });
    await waitFor(() => expect(screen.getByRole('button', { name: '排队发送' })).toBeEnabled());
    fireEvent.keyDown(input(), { key: 'Enter' });
    expect(send).toHaveBeenCalledWith({ draft: '附图读入期间继续写', images: [newImage] });
  });

  it('discards an older image callback after removal without unlocking a newer pending read', async () => {
    const readers = deferredImages();
    render(<Harness busy queue initialImages={[oldImage]} />);
    fireEvent.change(picker(), { target: { files: [imageFile()] } });
    await userEvent.click(screen.getByRole('button', { name: '移除附图1' }));
    fireEvent.change(picker(), { target: { files: [imageFile()] } });
    expect(readers).toHaveLength(2);
    readers[0].result = 'data:image/png;base64,c3RhbGU=';
    await act(async () => {
      readers[0].onload?.();
    });
    expect(screen.queryByRole('list', { name: '本轮附图' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '排队发送' })).toBeDisabled();
    await act(async () => {
      readers[1].onload?.();
    });
    expect(screen.getByAltText('本轮附图1')).toHaveAttribute('src', newImage);
    expect(document.body.innerHTML).not.toContain('c3RhbGU=');
  });

  it.each(['onload', 'onerror'] as const)('ignores image %s after the composer scope unmounts', async (callback) => {
    const readers = deferredImages(),
      images = vi.fn();
    const props: ComponentProps<typeof LiveComposer> = {
      draft: '合成旧scope',
      busy: true,
      capabilities: { queueWhileBusy: true },
      images: [],
      setText: vi.fn(),
      setImages: images,
      send: vi.fn(),
      stop: vi.fn(),
    };
    const old = render(<LiveComposer {...props} />);
    fireEvent.change(picker(), { target: { files: [imageFile()] } });
    old.unmount();
    render(<Harness busy queue />);
    await act(async () => {
      readers[0][callback]?.();
    });
    expect(images).not.toHaveBeenCalled();
    expect(screen.queryByRole('list', { name: '本轮附图' })).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not overwrite externally replaced attachments with an earlier read', async () => {
    const readers = deferredImages(),
      setImages = vi.fn();
    const props: ComponentProps<typeof LiveComposer> = {
      draft: '合成当前scope',
      busy: true,
      capabilities: { queueWhileBusy: true },
      images: [],
      setText: vi.fn(),
      setImages,
      send: vi.fn(),
      stop: vi.fn(),
    };
    const view = render(<LiveComposer {...props} />);
    fireEvent.change(picker(), { target: { files: [imageFile()] } });
    view.rerender(<LiveComposer {...props} images={[oldImage]} />);
    await act(async () => {
      readers[0].onload?.();
    });
    expect(setImages).not.toHaveBeenCalled();
    expect(screen.getByAltText('本轮附图1')).toHaveAttribute('src', oldImage);
    expect(screen.getByRole('button', { name: '排队发送' })).toBeEnabled();
  });

  it('returns an invalid image to an editable draft without claiming it was attached', async () => {
    render(<Harness busy queue />);
    fireEvent.change(picker(), { target: { files: [new File(['synthetic'], 'x.svg', { type: 'image/svg+xml' })] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('JPEG、PNG、WebP');
    expect(screen.queryByRole('list', { name: '本轮附图' })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: '排队发送' })).toBeEnabled());
  });
});

const item = (id: string, state: QueueItem['state'], extra: Partial<QueueItem> = {}): QueueItem => ({
  id,
  state,
  request_id: `request-${id}`,
  after_run_id: 'synthetic-run',
  text: `合成排队消息${id}`,
  images: [],
  created_at_ms: Date.parse('2026-10-21T08:01:00+08:00'),
  ...extra,
});
describe('queue list acknowledgement states', () => {
  it('renders a semantic list without promoting pending, canceling or failed to received', async () => {
    const cancel = vi.fn(),
      retry = vi.fn();
    render(
      <QueueList
        items={[
          item('pending', 'pending'),
          item('queued', 'queued', { images: [oldImage] }),
          item('canceling', 'canceling'),
          item('failed', 'failed', { failed_action: 'cancel', error: '取消尚未确认' }),
        ]}
        onCancel={cancel}
        onRetry={retry}
      />,
    );
    const list = screen.getByRole('list', { name: '排队消息列表' });
    const [pending, queued, canceling, failed] = within(list).getAllByRole('listitem');
    expect(within(pending).getByRole('status')).toHaveTextContent('正在接收，尚未确认');
    expect(within(pending).queryByRole('button')).not.toBeInTheDocument();
    expect(within(queued).getByRole('status')).toHaveTextContent('已收到，这段说完一起看');
    expect(queued).toHaveTextContent('08:01（北京时间）');
    expect(queued).toHaveTextContent('附图 1 张');
    expect(within(canceling).getByRole('status')).toHaveTextContent('正在取消，尚未收到确认');
    expect(within(canceling).queryByRole('button')).not.toBeInTheDocument();
    expect(within(failed).getByRole('status')).toHaveTextContent('取消尚未确认');
    await userEvent.click(within(queued).getByRole('button', { name: '取消排队' }));
    await userEvent.click(within(failed).getByRole('button', { name: '重试取消' }));
    await userEvent.click(within(failed).getByRole('button', { name: '取消排队' }));
    expect(cancel.mock.calls).toEqual([['queued'], ['failed']]);
    expect(retry).toHaveBeenCalledWith('failed');
  });
  it('keeps failed enqueue text and attachments available for a retry of that item', async () => {
    const retry = vi.fn();
    render(
      <QueueList
        items={[item('enqueue', 'failed', { failed_action: 'enqueue', images: [oldImage, newImage] })]}
        onCancel={vi.fn()}
        onRetry={retry}
      />,
    );
    expect(screen.getByText('合成排队消息enqueue')).toBeVisible();
    expect(screen.getByText('附图 2 张')).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent('这次尚未确认，请重试');
    await userEvent.click(screen.getByRole('button', { name: '重试排队发送' }));
    expect(retry).toHaveBeenCalledWith('enqueue');
  });
  it('does not render an empty queue as if anything was pending or received', () => {
    render(<QueueList items={[]} onCancel={vi.fn()} onRetry={vi.fn()} />);
    expect(screen.queryByRole('region', { name: '排队消息' })).not.toBeInTheDocument();
  });
});
