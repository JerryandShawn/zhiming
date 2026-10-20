import { Answer } from '../../chat/Answers';
import type { MemoryCommands } from '../../chat/interactions/contracts';
import { Button, Tag } from '../../components/ui/Controls';
import type { RecoveryPort } from './types';
import { useRecovery } from './useRecovery';
import './recovery.css';

const readOnlyMemory: MemoryCommands = {
  supports: () => false,
  async execute() {
    throw new Error('恢复预览只展示回执，不修改记忆。');
  },
};
const labels = {
  connecting: '正在建立本地连接…',
  open: '本地事件流已连接',
  reconnecting: '连接中断，正在从已确认位置补上…',
  closed: '本轮恢复演示已完成',
  failed: '这次没有恢复完整，已显示的内容保留',
  aborted: '已停止本地恢复演示，已显示的内容保留',
} as const;

export default function RecoveryPreview({ port, onBack }: { port?: RecoveryPort; onBack?: () => void }) {
  const demo = useRecovery(port);
  return (
    <section
      className="page recovery-preview stack"
      data-runtime="night-recovery"
      data-connection={demo.connection.phase}
      data-transport={demo.mode}
      data-last-event-id={demo.result?.lastEventId ?? ''}
      data-complete={demo.result?.reason === 'final'}
      aria-labelledby="recovery-title">
      <header className="stack small">
        <h1 id="recovery-title">断线恢复预览</h1>
        <div>
          <Tag>仅离线合成演示</Tag>
        </div>
        <p>先收到旧片段，再补发确认过的完整正文。重复事件只显示一次。</p>
        <p className="meta">
          {demo.mode === 'memory' ? '当前只使用页面内存，不发网络请求。' : '当前只连接本机前端测试路径，不访问后端。'}
        </p>
        <p className="meta">这里不代表真实服务已经支持补发；不会读取或清空普通对话的草稿。</p>
      </header>
      <div className="recovery-connection stack small" aria-label="恢复连接状态">
        <p role="status">{labels[demo.connection.phase]}</p>
        <p className="meta">
          已自动重连 {demo.connection.attempt} 次
          {demo.result?.lastEventId ? ` · 最后确认序号 ${demo.result.lastEventId}` : ''}
        </p>
        {demo.result?.error && <p role="alert">{demo.result.error}</p>}
      </div>
      <div className="recovery-answer" aria-label="恢复后的对话">
        <Answer key={demo.version} state={demo.state} memoryCommands={readOnlyMemory} />
      </div>
      <div className="row wrap recovery-actions">
        <Button onClick={demo.replay}>重放恢复演示</Button>
        <Button disabled={!demo.running} onClick={demo.stop}>
          停止恢复
        </Button>
        {['failed', 'aborted'].includes(demo.connection.phase) && <Button onClick={demo.replay}>重试连接</Button>}
        <a
          className="button primary"
          href="#/chat"
          onClick={(event) => {
            demo.stop();
            if (onBack) {
              event.preventDefault();
              onBack();
            }
          }}>
          回普通对话
        </a>
      </div>
    </section>
  );
}
