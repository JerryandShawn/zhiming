import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OfflineBanner } from '../src/pwa/OfflineBanner';
import { trackOfflineTypography } from '../src/pwa/typography';

const originalWorker = Object.getOwnPropertyDescriptor(navigator, 'serviceWorker');
afterEach(() => {
  if (originalWorker) Object.defineProperty(navigator, 'serviceWorker', originalWorker);
  else Reflect.deleteProperty(navigator, 'serviceWorker');
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute('data-network');
});
async function setup(online = true) {
  vi.resetModules();
  vi.stubGlobal('isSecureContext', true);
  vi.spyOn(document, 'readyState', 'get').mockReturnValue('complete');
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(online);
  const base = new URL('/', location.href);
  const registration = { scope: base.href, active: { scriptURL: new URL('shell-sw.js', base).href } };
  const worker = { register: vi.fn(async () => registration), getRegistration: vi.fn(async () => registration) };
  Object.defineProperty(navigator, 'serviceWorker', { value: worker, configurable: true });
  const { registerShellWorker } = await import('../src/pwa/register');
  return { registerShellWorker, worker, base, registration };
}

describe('PWA registration and offline announcement', () => {
  it('selects local typography before an offline render and restores web fonts on reconnection', () => {
    let online = false;
    vi.spyOn(navigator, 'onLine', 'get').mockImplementation(() => online);
    const dispose = trackOfflineTypography();
    expect(document.documentElement).toHaveAttribute('data-network', 'offline');
    online = true;
    window.dispatchEvent(new Event('online'));
    expect(document.documentElement).toHaveAttribute('data-network', 'online');
    dispose();
    online = false;
    window.dispatchEvent(new Event('offline'));
    expect(document.documentElement).toHaveAttribute('data-network', 'online');
  });
  it('does not register when explicitly disabled or when the container is insecure', async () => {
    const { registerShellWorker, worker } = await setup();
    expect(await registerShellWorker({ enabled: false })).toEqual({ status: 'disabled' });
    vi.stubGlobal('isSecureContext', false);
    expect(await registerShellWorker({ enabled: true })).toEqual({ status: 'unsupported' });
    expect(worker.register).not.toHaveBeenCalled();
  });
  it('registers once after load, with same-origin scope and no forced activation', async () => {
    const { registerShellWorker, worker, base } = await setup();
    vi.spyOn(document, 'readyState', 'get').mockReturnValue('loading');
    const first = registerShellWorker({ enabled: true });
    const second = registerShellWorker({ enabled: true });
    expect(first).toBe(second);
    await act(async () => {
      await Promise.resolve();
    });
    expect(worker.register).not.toHaveBeenCalled();
    window.dispatchEvent(new Event('load'));
    expect(await first).toMatchObject({ status: 'registered' });
    expect(worker.register).toHaveBeenCalledExactlyOnceWith(new URL('shell-sw.js', base), {
      scope: '/',
      updateViaCache: 'none',
    });
  });
  it('reuses its active registration offline without requesting a script update', async () => {
    const { registerShellWorker, worker, registration, base } = await setup(false);
    expect(await registerShellWorker({ enabled: true })).toEqual({ status: 'registered', registration });
    expect(worker.getRegistration).toHaveBeenCalledExactlyOnceWith(base.href);
    expect(worker.register).not.toHaveBeenCalled();
  });
  it('does not create an offline registration or reuse an unrelated worker', async () => {
    const { registerShellWorker, worker } = await setup(false);
    worker.getRegistration.mockResolvedValue({
      scope: new URL('/', location.href).href,
      active: { scriptURL: new URL('/other-sw.js', location.href).href },
    });
    expect(await registerShellWorker({ enabled: true })).toMatchObject({ status: 'failed' });
    expect(worker.register).not.toHaveBeenCalled();
  });
  it('degrades gracefully when the container rejects registration', async () => {
    const { registerShellWorker, worker } = await setup();
    worker.register.mockRejectedValue(new Error('synthetic unsupported container'));
    expect(await registerShellWorker({ enabled: true })).toMatchObject({ status: 'failed' });
  });
  it('announces offline state in a named landmark and removes the banner after reconnection', () => {
    let online = true;
    vi.spyOn(navigator, 'onLine', 'get').mockImplementation(() => online);
    render(<OfflineBanner />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    act(() => {
      online = false;
      window.dispatchEvent(new Event('offline'));
    });
    expect(screen.getByRole('complementary', { name: '网络状态' })).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent('离线中');
    expect(screen.getByRole('status')).toHaveTextContent('请手动继续');
    act(() => {
      online = true;
      window.dispatchEvent(new Event('online'));
    });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
