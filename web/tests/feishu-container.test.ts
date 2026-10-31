import { describe, expect, it, vi } from 'vitest';
import { detectContainer, disconnectedSignInPort } from '../src/embed/feishu';

describe('container evidence stays separate from authentication', () => {
  it('recognizes the existing case-insensitive whole-word Lark and Feishu UA hints', () => {
    for (const [userAgent, token] of [['Mozilla/5.0 Lark/7.0', 'lark'], ['Mozilla/5.0 (fEiShU)', 'feishu']]) {
      expect(detectContainer(userAgent)).toEqual({
        host: 'feishu',
        evidence: { source: 'user-agent', adapter: 'not-provided', matchedToken: token },
        auth: { status: 'not-connected' },
      });
    }
  });

  it('preserves browser and substring boundaries instead of treating similar names as hosts', () => {
    for (const userAgent of ['', 'Mozilla/5.0 Chrome/140', 'NotFeishu', 'FeishuClient', 'Larkish', 'x_Lark']) {
      expect(detectContainer(userAgent).host).toBe('browser');
    }
  });

  it('uses an explicit trusted adapter report ahead of a possibly spoofed UA hint', () => {
    expect(detectContainer('Chrome', () => 'feishu')).toEqual({
      host: 'feishu', evidence: { source: 'trusted-adapter', adapter: 'reported' }, auth: { status: 'not-connected' },
    });
    expect(detectContainer('Feishu/7', () => 'browser').host).toBe('browser');
  });

  it('falls back to the unchanged UA detection when an adapter is unavailable or throws', () => {
    expect(detectContainer('Lark/7', () => undefined).evidence).toEqual({
      source: 'user-agent', adapter: 'unavailable', matchedToken: 'lark',
    });
    expect(detectContainer('Chrome', () => { throw new Error('adapter unavailable'); })).toEqual({
      host: 'browser', evidence: { source: 'user-agent', adapter: 'failed' }, auth: { status: 'not-connected' },
    });
  });

  it('never upgrades container detection into an authenticated sign-in state', async () => {
    expect(detectContainer('Feishu/7', () => 'feishu').auth.status).toBe('not-connected');
    expect(disconnectedSignInPort.available).toBe(false);
    expect(disconnectedSignInPort.status).toBe('not-connected');
    await expect(disconnectedSignInPort.request()).resolves.toEqual({ status: 'unavailable', reason: 'not-connected' });
  });

  it('does not use network transports or SDKs when the disconnected port is requested repeatedly', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const xhrSpy = vi.spyOn(XMLHttpRequest.prototype, 'open');
    const socketSpy = vi.spyOn(globalThis, 'WebSocket');
    try {
      await Promise.all([disconnectedSignInPort.request(), disconnectedSignInPort.request()]);
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(xhrSpy).not.toHaveBeenCalled();
      expect(socketSpy).not.toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
      xhrSpy.mockRestore();
      socketSpy.mockRestore();
    }
  });
});
