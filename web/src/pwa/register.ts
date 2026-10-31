export type ShellRegistration = {
  status: 'registered' | 'unsupported' | 'disabled' | 'failed';
  registration?: ServiceWorkerRegistration;
  message?: string;
};
let pending: Promise<ShellRegistration> | undefined;
export function registerShellWorker(options: { enabled?: boolean } = {}): Promise<ShellRegistration> {
  if (!(options.enabled ?? import.meta.env.PROD)) return Promise.resolve({ status: 'disabled' });
  if (pending) return pending;
  pending = Promise.resolve().then(async (): Promise<ShellRegistration> => {
    try {
      if (!window.isSecureContext || !('serviceWorker' in navigator)) return { status: 'unsupported' };
      if (document.readyState !== 'complete')
        await new Promise<void>((resolve) => window.addEventListener('load', () => resolve(), { once: true }));
      const base = new URL(import.meta.env.BASE_URL, document.baseURI);
      if (base.origin !== location.origin) return { status: 'disabled' };
      const script = new URL('shell-sw.js', base);
      if (navigator.onLine === false) {
        const existing = await navigator.serviceWorker.getRegistration(base.href);
        if (existing?.scope === base.href && existing.active?.scriptURL === script.href)
          return { status: 'registered', registration: existing };
        return { status: 'failed', message: '离线外壳尚未就绪，请连接网络后重试。' };
      }
      const registration = await navigator.serviceWorker.register(script, {
        scope: base.pathname,
        updateViaCache: 'none',
      });
      // Updates wait for old pages to close. Never reload or claim an active conversation.
      return { status: 'registered', registration };
    } catch {
      return { status: 'failed', message: '当前容器暂不支持离线外壳，联网使用不受影响。' };
    }
  });
  return pending;
}
