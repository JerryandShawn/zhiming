import { useSyncExternalStore } from 'react';
import { AppearancePrivacy } from './AppearancePrivacy';
import { ContactForm } from './ContactForm';
import { Devices } from './Devices';
import { ReportForm } from './ReportForms';
import type { SettingsPort } from './types';
import './settings.css';

export default function SettingsPage({ port }: { port: SettingsPort }) {
  const state = useSyncExternalStore(port.subscribe, port.getSnapshot);
  return (
    <div
      className="page night-settings"
      data-page="settings"
      data-runtime="night-settings"
      data-revision={state.revision}>
      <header className="page-heading">
        <h1>设置</h1>
        <p className="meta">本地交互演示，报告和设备操作不会影响真实账号。</p>
      </header>
      <div className="page-grid">
        <div>
          <section className="setting-group" aria-label="晨报与周期报告">
            <h2>晨报与周期报告</h2>
            <p className="meta">北京时间 · 提前 15 分钟准备。显示的是已保存设置的预览。</p>
            {state.reports.schedules.map((item) => (
              <ReportForm key={item.kind} item={item} port={port} />
            ))}
          </section>
          <ContactForm item={state.contact} port={port} />
        </div>
        <aside>
          <AppearancePrivacy />
          <Devices items={state.devices} revision={state.revision} ended={state.localSessionEnded} port={port} />
        </aside>
      </div>
    </div>
  );
}
