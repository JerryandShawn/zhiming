/* Real legacy DOM and JavaScript against an explicitly isolated HTTP origin. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');

async function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const base = new URL(input.origin);
  assert.equal(base.hostname, '127.0.0.1');
  assert.equal(base.protocol, 'http:');
  const root = path.resolve(__dirname, '../../..');
  const html = await fetch(new URL('/', base)).then(r => r.text());
  const dom = new JSDOM(html, { url: base.href, runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const calls = [];
  try {
    w.TextDecoder = TextDecoder;
    w.ResizeObserver = class { observe() {} disconnect() {} };
    w.fetch = async (target, options) => {
      const url = new URL(target, base);
      assert.equal(url.origin, base.origin, 'legacy DOM must never contact an external origin');
      calls.push({ path: url.pathname, method: options?.method || 'GET' });
      return fetch(url, options);
    };
    w.localStorage.setItem('mjt_token', 'synthetic-dom-owner');
    w.localStorage.setItem('mjt_session', 'shared');
    for (const file of ['marked.js', 'purify.js']) {
      w.eval(fs.readFileSync(path.join(root, 'static/vendor', file), 'utf8'));
    }
    const source = fs.readFileSync(path.join(root, 'static/app.js'), 'utf8');
    const marker = "$('#todayLabel').textContent=";
    assert.equal(source.split(marker).length, 2, 'legacy boot boundary must be reviewed if changed');
    w.eval(source.split(marker)[0] + '\n globalThis.legacyProbe = { sendChat, loadHistory };');
    if (input.message) await w.legacyProbe.sendChat(input.message);
    else await w.legacyProbe.loadHistory();
    const flow = w.document.querySelector('#chatFlow');
    const rendered = flow.textContent;
    for (const text of input.expected) assert.ok(rendered.includes(text), 'expected committed answer missing in DOM');
    assert.equal(flow.querySelectorAll('[role="alert"]').length, 0, 'legacy page rendered an error');
    assert.equal(w.document.querySelector('#sendBtn').disabled, false);
    console.log(JSON.stringify({
      assistant_nodes: flow.querySelectorAll('.answer-reading').length,
      receipt_nodes: flow.querySelectorAll('.memory-notice').length,
      post_count: calls.filter(x => x.method === 'POST').length,
      recovery_count: calls.filter(x => x.path.startsWith('/api/chat/')).length,
      history_count: calls.filter(x => x.path === '/api/history').length,
      run_ids: [...flow.querySelectorAll('[data-core-run]')].map(x => x.dataset.coreRun),
    }));
  } finally { w.close(); }
}
main().catch(error => { console.error(error.stack); process.exitCode = 1; });
