import { useState } from 'react';
import { Laptop, AlertTriangle } from 'lucide-react';
import * as Dialog from '@radix-ui/react-dialog';
import { Button, Tag } from '../../components/ui/Controls';
import { Panel } from '../../components/ui/Overlays';
import type { MockDevice, SettingsPort } from './types';
import { useSettingsCommand } from './useSettingsCommand';

function Revoke({ item, port }: { item: MockDevice; port: SettingsPort }) {
  const operation = useSettingsCommand(port);
  return (
    <div className="stack">
      <p className="row">
        <AlertTriangle className="icon" aria-hidden="true" />
        这只吊销合成设备的本地会话，不会修改真实登录。
      </p>
      {operation.error && <p role="alert">{operation.error}</p>}
      {operation.saved && <p role="status">已吊销此合成设备（本地演示）。</p>}
      <Button
        loading={operation.busy}
        disabled={operation.conflict || operation.saved}
        onClick={() =>
          void operation.run(
            { type: 'device-revoke', id: item.id, expectedRevision: item.revision, requestId: crypto.randomUUID() },
            (receipt, command) =>
              command.type === 'device-revoke' &&
              receipt.write_status === 'revoked' &&
              receipt.device?.id === command.id &&
              receipt.device.status === 'revoked' &&
              !receipt.device.current,
          )
        }>
        {operation.hasPending ? '重试原吊销操作' : '确认吊销（本地演示）'}
      </Button>
      <Dialog.Close asChild>
        <Button variant="ghost">取消</Button>
      </Dialog.Close>
    </div>
  );
}
export function Devices({
  items,
  port,
  revision,
  ended,
}: {
  items: MockDevice[];
  port: SettingsPort;
  revision: number;
  ended: boolean;
}) {
  const logout = useSettingsCommand(port),
    [showLogout, setShowLogout] = useState(false);
  return (
    <section className="setting-group" aria-label="设备与登录">
      <h2>设备与登录</h2>
      <p className="meta">以下都是合成设备。此处不会读取或撤销你的真实登录凭据。</p>
      <ul className="settings-devices">
        {items.map((item) => (
          <li
            className="settings-device"
            data-device-id={item.id}
            data-status={item.status}
            data-revision={item.revision}
            key={item.id}>
            <div className="row">
              <Laptop className="icon" aria-hidden="true" />
              <div>
                <h3>{item.label}</h3>
                <p className="meta">最近使用 {item.lastUsedAt}</p>
              </div>
              {item.current && <Tag>当前设备</Tag>}
              {item.status === 'revoked' && <Tag>已吊销（本地演示）</Tag>}
            </div>
            <Panel
              title="吊销这台设备？"
              description="请先核对设备，确认前不会吊销。"
              trigger={
                <Button variant="ghost" disabled={item.current || item.status !== 'active'}>
                  吊销此设备
                </Button>
              }>
              <Revoke item={item} port={port} />
            </Panel>
          </li>
        ))}
      </ul>
      <Button variant="ghost" disabled={ended} onClick={() => setShowLogout(true)}>
        退出本地演示
      </Button>
      {showLogout && !ended && (
        <div className="stack small">
          <p>只结束这次本地演示，不退出真实账号。</p>
          <Button
            disabled={logout.conflict}
            loading={logout.busy}
            onClick={() =>
              void logout.run(
                { type: 'local-logout', expectedRevision: revision, requestId: crypto.randomUUID() },
                (receipt) => receipt.write_status === 'saved' && port.getSnapshot().localSessionEnded,
              )
            }>
            确认退出本地演示
          </Button>
          <Button variant="ghost" onClick={() => setShowLogout(false)}>
            取消退出
          </Button>
        </div>
      )}
      {logout.error && <p role="alert">{logout.error}</p>}
      {ended && <p role="status">本地演示会话已结束，真实账号保持原状。</p>}
    </section>
  );
}
