import { useSyncExternalStore } from 'react';
import './pwa.css';
function subscribe(listener: () => void) {
  window.addEventListener('online', listener);
  window.addEventListener('offline', listener);
  return () => {
    window.removeEventListener('online', listener);
    window.removeEventListener('offline', listener);
  };
}
export function useOnlineStatus() {
  return useSyncExternalStore(
    subscribe,
    () => navigator.onLine !== false,
    () => true,
  );
}
export function OfflineBanner() {
  const online = useOnlineStatus();
  return online ? null : (
    <aside className="pwa-offline" aria-label="网络状态">
      <p role="status" aria-live="polite">
        <strong>离线中</strong>
        <span>暂时无法发送或同步。恢复连接后，请手动继续。</span>
      </p>
    </aside>
  );
}
