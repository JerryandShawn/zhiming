import { createHash, webcrypto } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Script } from 'node:vm';
import { describe, expect, it, vi } from 'vitest';
import { selectShellFiles, SHELL_FONTS } from '../pwa.plugin';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = readFileSync(resolve(root, 'public/pwa/shell-runtime.js'), 'utf8');
const origin = 'https://shell.example';
const prefix = 'mingjing-shell-v1:%2F:';
const built: Record<string, string> = {
  'index.html': '<!doctype html><html><body><div id="root"></div></body></html>',
  'assets/app-1234abcd.js': 'console.log("static shell only");',
  'assets/app-1234abcd.css': 'body{color:#222}',
};
function setup(overrides: Record<string, string> = {}) {
  const resources = { ...built, ...overrides };
  const assets = Object.entries(built).map(([path, body]) => ({
    path,
    bytes: Buffer.byteLength(body),
    sha256: createHash('sha256').update(body).digest('hex'),
  }));
  const stores = new Map<string, Map<string, Response>>();
  const writes: { name: string; url: string; body: string }[] = [];
  const address = (request: Request | string) => (typeof request === 'string' ? request : request.url);
  const caches = {
    keys: async () => [...stores.keys()],
    delete: vi.fn(async (name: string) => stores.delete(name)),
    open: async (name: string) => {
      if (!stores.has(name)) stores.set(name, new Map());
      const store = stores.get(name)!;
      return {
        match: async (request: Request | string) => store.get(address(request))?.clone(),
        put: async (request: Request | string, response: Response) => {
          const url = address(request);
          writes.push({ name, url, body: await response.clone().text() });
          store.set(url, response.clone());
        },
      };
    },
  };
  const fetcher = vi.fn(async (request: Request | string) => {
    const path = new URL(address(request)).pathname.slice(1);
    return path in resources
      ? new Response(resources[path], { headers: { 'Content-Type': 'text/plain' } })
      : new Response('NETWORK_ONLY_USER_DATA', { headers: { 'Content-Type': 'application/json' } });
  });
  const listeners = new Map<string, (event: unknown) => void>();
  const claim = vi.fn(),
    skipWaiting = vi.fn();
  const self = {
    __MINGJING_SHELL__: { version: 'new-version', assets },
    registration: { scope: `${origin}/` },
    location: { origin },
    clients: { claim },
    skipWaiting,
    addEventListener: (name: string, handler: (event: unknown) => void) => listeners.set(name, handler),
  };
  new Script(source).runInNewContext({
    self,
    caches,
    fetch: fetcher,
    Request,
    Response,
    URL,
    crypto: webcrypto,
    Uint8Array,
    console,
  });
  const lifecycle = async (type: string) => {
    let work: Promise<unknown> | undefined;
    listeners.get(type)!({
      waitUntil: (promise: Promise<unknown>) => {
        work = promise;
      },
    });
    await work;
  };
  const request = async (url: string, init: RequestInit = {}, navigation = false) => {
    const value = new Request(new URL(url, origin), init);
    if (navigation) Object.defineProperty(value, 'mode', { value: 'navigate' });
    let intercepted: Promise<Response> | undefined;
    listeners.get('fetch')!({
      request: value,
      respondWith: (response: Promise<Response>) => {
        intercepted = response;
      },
    });
    return { response: await (intercepted ?? fetcher(value)), intercepted: Boolean(intercepted) };
  };
  return { stores, writes, caches, fetcher, listeners, claim, skipWaiting, lifecycle, request };
}

describe('build whitelist for a static, content-free PWA shell', () => {
  it('selects only hashed build code and explicitly limited public shell assets', () => {
    const selected = selectShellFiles(
      [
        'assets/app-1234abcd.js',
        'assets/app-1234abcd.css',
        'assets/chat.json',
        'assets/user-1234abcd.png',
        'assets/not-hashed.js',
        '../api/messages',
      ],
      [
        'pwa/manifest.webmanifest',
        'pwa/seal.svg',
        'pwa/private.json',
        'fonts/fonts.css',
        ...SHELL_FONTS.map((name) => `fonts/${name}`),
        'fonts/noto-sans-sc-1-wght-normal.woff2',
      ],
    );
    expect(selected).toContain('index.html');
    expect(selected).toContain('assets/app-1234abcd.js');
    expect(selected.filter((name) => name.endsWith('.woff2'))).toHaveLength(4);
    expect(selected).not.toContain('assets/chat.json');
    expect(selected).not.toContain('assets/not-hashed.js');
    expect(selected).not.toContain('pwa/private.json');
    expect(selected).not.toContain('fonts/noto-sans-sc-1-wght-normal.woff2');
    expect(selected.some((name) => name.includes('..') || name.includes('/api/'))).toBe(false);
  });
  it('ships a standalone manifest and a native seal without an external font or image dependency', () => {
    const manifest = JSON.parse(readFileSync(resolve(root, 'public/pwa/manifest.webmanifest'), 'utf8'));
    expect(manifest).toMatchObject({ start_url: '../', scope: '../', display: 'standalone' });
    expect(manifest.icons[0]).toMatchObject({ src: 'seal.svg', type: 'image/svg+xml', purpose: 'any maskable' });
    const svg = readFileSync(resolve(root, 'public/pwa/seal.svg'), 'utf8');
    expect(svg).not.toMatch(/<image|<text|https?:\/\/(?!www\.w3\.org)/);
  });
});

describe('actual service worker runtime executed in an isolated browser-like realm', () => {
  it('preloads verified build bytes anonymously and keeps only those exact shell bodies', async () => {
    const sw = setup();
    await sw.lifecycle('install');
    expect(sw.writes.map((item) => new URL(item.url).pathname)).toEqual(Object.keys(built).map((path) => `/${path}`));
    expect(sw.writes.every((item) => !item.body.includes('NETWORK_ONLY_USER_DATA'))).toBe(true);
    for (const [request] of sw.fetcher.mock.calls) {
      expect(request).toBeInstanceOf(Request);
      const value = request as Request;
      expect(value.credentials).toBe('omit');
      expect(value.cache).toBe('no-store');
      expect(value.redirect).toBe('error');
    }
    expect([...sw.stores.keys()]).toEqual([prefix + 'new-version']);
  });
  it('rejects personalized or changed bytes at a whitelisted URL without deleting other caches', async () => {
    const sw = setup({ 'index.html': 'PRIVATE_CONVERSATION_IN_SERVER_RESPONSE' });
    sw.stores.set('other-application-data', new Map());
    await expect(sw.lifecycle('install')).rejects.toThrow('integrity');
    expect([...sw.stores.keys()]).toEqual(['other-application-data']);
    expect(sw.writes).toEqual([]);
  });
  it('never writes runtime navigation or user response bodies, and falls back only to built empty HTML', async () => {
    const sw = setup();
    await sw.lifecycle('install');
    const writes = sw.writes.length;
    sw.fetcher.mockImplementation(async () => new Response('RUNTIME_PRIVATE_DIALOG'));
    const online = await sw.request('/?night=demo', {}, true);
    expect(await online.response.text()).toBe('RUNTIME_PRIVATE_DIALOG');
    expect(sw.writes).toHaveLength(writes);
    sw.fetcher.mockRejectedValue(new Error('simulated offline'));
    const offline = await sw.request('/?night=demo', {}, true);
    expect(await offline.response.text()).toBe(built['index.html']);
    expect(sw.writes).toHaveLength(writes);
    const script = await sw.request('/assets/app-1234abcd.js');
    expect(await script.response.text()).toBe(built['assets/app-1234abcd.js']);
  });
  it.each([
    ['/api/chat', { method: 'POST', body: 'PRIVATE_USER_MESSAGE' }],
    ['/api/runs/run/events', { headers: { Accept: 'text/event-stream' } }],
    ['/assets/app-1234abcd.js', { headers: { Accept: 'text/event-stream' } }],
    ['/assets/app-1234abcd.js', { headers: { Authorization: 'Bearer PRIVATE_TOKEN' } }],
    ['/assets/app-1234abcd.js', { headers: { 'X-Token': 'PRIVATE_TOKEN' } }],
    ['/assets/app-1234abcd.js', { headers: { 'X-Custom-Token': 'PRIVATE_TOKEN' } }],
    ['/assets/app-1234abcd.js', { headers: { 'X-Api-Key': 'PRIVATE_TOKEN' } }],
    ['/uploads/private.png', {}],
    ['/api/profile', {}],
    ['/__test__/events-v1/runs/run/events', {}],
    ['/unknown.json', {}],
    ['/assets/unknown-1234abcd.js', {}],
    ['/assets/app-1234abcd.js?token=PRIVATE_TOKEN', {}],
    ['/assets/app-1234abcd.js?v=2', {}],
    ['https://different.example/assets/app-1234abcd.js', {}],
  ] as const)('keeps %s network-only with no runtime cache writes', async (url, init) => {
    const sw = setup();
    await sw.lifecycle('install');
    const count = sw.writes.length,
      calls = sw.fetcher.mock.calls.length;
    const outcome = await sw.request(url, init);
    expect(outcome.intercepted).toBe(false);
    expect(sw.fetcher.mock.calls.length).toBe(calls + 1);
    expect(sw.writes).toHaveLength(count);
    expect(sw.writes.some((item) => /PRIVATE_|NETWORK_ONLY/.test(item.body))).toBe(false);
  });
  it('does not turn token navigation or unknown navigation into a cached page', async () => {
    const sw = setup();
    await sw.lifecycle('install');
    expect((await sw.request('/?token=PRIVATE_TOKEN', {}, true)).intercepted).toBe(false);
    expect((await sw.request('/private-detail', {}, true)).intercepted).toBe(false);
  });
  it('cleans only this scope and prefix, without claiming or reloading old active clients', async () => {
    const sw = setup();
    await sw.lifecycle('install');
    for (const key of [prefix + 'old-version', 'mingjing-shell-v1:%2Fother%2F:old', 'unrelated-private-data'])
      sw.stores.set(key, new Map());
    await sw.lifecycle('activate');
    expect([...sw.stores.keys()]).toEqual([
      prefix + 'new-version',
      'mingjing-shell-v1:%2Fother%2F:old',
      'unrelated-private-data',
    ]);
    expect(sw.claim).not.toHaveBeenCalled();
    expect(sw.skipWaiting).not.toHaveBeenCalled();
    expect(sw.listeners.has('sync')).toBe(false);
    expect(sw.listeners.has('message')).toBe(false);
  });
});
