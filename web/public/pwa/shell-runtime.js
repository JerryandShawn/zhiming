/* Build-injected, immutable static shell only. No runtime response is ever written to CacheStorage. */
(() => {
  const config = self.__MINGJING_SHELL__;
  const scope = new URL(self.registration.scope);
  const prefix = `mingjing-shell-v1:${encodeURIComponent(scope.pathname)}:`;
  const cacheName = prefix + config.version;
  const indexUrl = new URL('index.html', scope).href;
  const allowed = new Map(
    config.assets.map((entry) => {
      const url = new URL(entry.path, scope);
      if (
        url.origin !== scope.origin ||
        !url.pathname.startsWith(scope.pathname) ||
        url.search ||
        url.hash ||
        !/^[a-f0-9]{64}$/.test(entry.sha256) ||
        !Number.isSafeInteger(entry.bytes)
      )
        throw new Error('Invalid shell manifest');
      return [url.href, entry];
    }),
  );
  function dataRequest(request, url) {
    return (
      request.method !== 'GET' ||
      url.origin !== scope.origin ||
      url.username ||
      url.password ||
      /\/(?:api|__test__|uploads?)(?:\/|$)/i.test(url.pathname) ||
      /text\/event-stream/i.test(request.headers.get('accept') || '') ||
      [...request.headers.keys()].some((key) => /authorization|token|api[-_]key/i.test(key)) ||
      [...url.searchParams.keys()].some((key) => /authorization|token|api[-_]key/i.test(key))
    );
  }
  async function install() {
    try {
      const cache = await caches.open(cacheName);
      for (const [url, entry] of allowed) {
        const request = new Request(url, { credentials: 'omit', cache: 'no-store', redirect: 'error' });
        const response = await fetch(request);
        if (!response.ok || response.redirected || response.type === 'opaque') throw new Error('Shell fetch failed');
        const bytes = await response.clone().arrayBuffer();
        const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
          .map((value) => value.toString(16).padStart(2, '0'))
          .join('');
        if (bytes.byteLength !== entry.bytes || hash !== entry.sha256) throw new Error('Shell integrity mismatch');
        await cache.put(request, response);
      }
    } catch (reason) {
      await caches.delete(cacheName);
      throw reason;
    }
  }
  self.addEventListener('install', (event) => event.waitUntil(install()));
  self.addEventListener('activate', (event) =>
    event.waitUntil(
      (async () => {
        for (const key of await caches.keys())
          if (key.startsWith(prefix) && key !== cacheName) await caches.delete(key);
        // No skipWaiting, clients.claim, reload, message queue or background synchronization.
      })(),
    ),
  );
  self.addEventListener('fetch', (event) => {
    const request = event.request,
      url = new URL(request.url);
    if (dataRequest(request, url)) return;
    const navigation =
      request.mode === 'navigate' && [scope.pathname, new URL(indexUrl).pathname].includes(url.pathname);
    if (navigation) {
      event.respondWith(
        fetch(request).catch(async () => {
          const cache = await caches.open(cacheName),
            shell = await cache.match(indexUrl);
          return (
            shell ||
            new Response('离线外壳尚未就绪，请连接网络后重试。', {
              status: 503,
              headers: { 'Content-Type': 'text/plain; charset=utf-8' },
            })
          );
        }),
      );
      return;
    }
    if (url.search || !allowed.has(url.href)) return;
    event.respondWith(
      (async () => {
        const cache = await caches.open(cacheName);
        return (await cache.match(url.href)) || fetch(request);
      })(),
    );
  });
})();
