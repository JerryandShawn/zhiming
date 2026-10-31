import { useState } from 'react';
import { api, useAuth } from '../api/client';
import { pendingPayload } from '../api/operations';
import { useResource } from '../api/useResource';
import { Button, Segmented, Switch } from '../components/ui/Controls';
import { useUi, type Theme } from '../state';
import { ResourceState, useCommand } from './common';
import ReportSchedule, { validSchedules } from './ReportSchedule';
import Reports from './Reports';
import type { Snapshot, Schedules } from './types';

function MemorySettings({ snapshot }: { snapshot: Snapshot }) {
  const scope = 'settings:memory';
  const pending = pendingPayload<{ expected_revision: number; settings: { auto_save_low_sensitivity: boolean } }>(
    scope,
  );
  const [enabled, setEnabled] = useState(
    pending?.settings.auto_save_low_sensitivity ?? snapshot.settings.auto_save_low_sensitivity !== false,
  );
  const [version, setVersion] = useState(pending?.expected_revision ?? snapshot.revision);
  const command = useCommand(scope);
  async function save() {
    const result = await command.submit<{ revision: number; kind: string; settings: Snapshot['settings'] }>(
      'PATCH',
      '/api/state/settings',
      {
        expected_revision: version,
        settings: { auto_save_low_sensitivity: enabled },
      },
      (value) =>
        value.kind === 'settings' &&
        Number.isInteger(value.revision) &&
        value.settings.auto_save_low_sensitivity === enabled,
    );
    if (result) {
      setVersion(result.revision);
      command.setStatus('已收到记忆设置回执。');
    }
  }
  async function refresh() {
    try {
      const latest = await api<Snapshot>('/api/state');
      setVersion(latest.revision);
      command.unlock();
    } catch {
      command.setStatus('最新设置读取失败，草稿仍保留。');
    }
  }
  return (
    <section className="setting-group">
      <h2>记忆与隐私</h2>
      <div className="setting-row">
        <span>自动保存低敏感偏好与约束</span>
        <Switch
          label="自动保存低敏感偏好与约束"
          checked={enabled}
          onChange={setEnabled}
          disabled={command.busy || Boolean(pending)}
        />
      </div>
      <p className="meta">出生资料仍需明确授权。每次保存均以回答下方的实际回执为准。</p>
      <Button loading={command.busy} disabled={command.conflict} onClick={() => void save()}>
        {pending ? '重试原记忆设置' : '保存记忆设置'}
      </Button>
      {command.conflict && <Button onClick={() => void refresh()}>读取最新设置，保留草稿</Button>}
      <p role="status">{command.status}</p>
      <a className="text-link quiet-link" href="#/me?section=memory">
        查看、更正或删除记忆
      </a>
    </section>
  );
}
export default function Settings() {
  const reports = useResource<Schedules>('/api/reports/schedules');
  const snapshot = useResource<Snapshot>('/api/state');
  const health = useResource<{ model?: string }>('/api/health');
  const theme = useUi((state) => state.theme),
    setTheme = useUi((state) => state.setTheme);
  const setToken = useAuth((state) => state.setToken);
  if (location.hash.startsWith('#/reports')) return <Reports />;
  return (
    <div className="page" data-page="settings">
      <header className="page-heading desktop-heading">
        <h1>设置</h1>
      </header>
      <div className="page-grid">
        <div>
          <section className="setting-group">
            <h2>晨报与周期报告</h2>
            <p className="meta">北京时间（Asia/Shanghai），提前 15 分钟准备。这里只调整已有渠道的时间与启用状态。</p>
            <ResourceState
              loading={reports.isPending}
              error={reports.error}
              retry={() => {
                void reports.refetch();
              }}
            />
            {reports.data &&
              (validSchedules(reports.data) ? (
                reports.data.schedules.map((item) => <ReportSchedule key={item.kind} item={item} />)
              ) : (
                <p role="alert">报告时间表不完整，暂不能修改。</p>
              ))}
            <a className="text-link quiet-link" href="#/reports">
              查看报告归档
            </a>
          </section>
          <section className="setting-group">
            <h2>主动联系与免打扰</h2>
            <p>自动跟进、每日联系上限与免打扰设置正在准备。</p>
            <Button disabled>调整主动联系</Button>
          </section>
          <section className="setting-group">
            <h2>模型</h2>
            <p>当前模型：{health.data?.model ?? '尚未读取'}</p>
            <p className="meta">模型切换暂不可用。</p>
          </section>
        </div>
        <aside>
          <section className="setting-group">
            <h2>外观</h2>
            <Segmented<Theme>
              label="外观主题"
              value={theme}
              onChange={setTheme}
              options={[
                { value: 'system', label: '跟随系统' },
                { value: 'light', label: '宣纸' },
                { value: 'dark', label: '夜墨' },
              ]}
            />
          </section>
          <ResourceState
            loading={snapshot.isPending}
            error={snapshot.error}
            retry={() => {
              void snapshot.refetch();
            }}
          />
          {snapshot.data && <MemorySettings snapshot={snapshot.data} />}
          <section className="setting-group">
            <h2>设备与登录</h2>
            <p className="meta">退出后需要重新输入网站口令。其他设备管理暂不可用。</p>
            <Button onClick={() => setToken('')}>退出登录</Button>
            <Button disabled>吊销其他设备</Button>
          </section>
          <section className="setting-group">
            <h2>无痕模式</h2>
            <p className="meta">无痕对话正在准备，暂不可用。请核对每次记忆回执。</p>
            <Button disabled>开启无痕对话</Button>
          </section>
        </aside>
      </div>
    </div>
  );
}
