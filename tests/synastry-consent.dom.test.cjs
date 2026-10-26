const fs = require('fs');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const code = fs.readFileSync('static/synastry-consent.js', 'utf8');
const html = fs.readFileSync('static/index.html', 'utf8');
assert(html.indexOf('/static/synastry-consent.js') < html.indexOf('/static/app.js'));
const fixture = { id: 'native-card', revision: 1, kind: 'friendship', state: 'pending_confirmation',
  message: '合盘会用到〈<img src=x onerror="window.bad=1">〉的出生资料。只做这一次，不保存结果、不转发。' };
const flush = () => new Promise(resolve => setImmediate(resolve));

function setup() {
  const dom = new JSDOM('<main id="cards"></main>', { runScripts: 'outside-only', url: 'https://fixture.invalid' });
  const w = dom.window;
  // Strict eval has its own lexical scope; expose the script's actual entry only.
  w.eval(code + '\nwindow.renderSynastryConsents = renderSynastryConsents;');
  const root = w.document.querySelector('#cards');
  return { w, root };
}

(async () => {
  const { w, root } = setup();
  const writes = [];
  let fail = true;
  const apiJson = async (path, options) => {
    if (!options) {
      assert.equal(path, '/api/synastry/consents?conversation_id=conversation%2Fa');
      return [fixture];
    }
    assert.equal(path, '/api/synastry/consents/native-card/confirm');
    writes.push(JSON.parse(options.body));
    assert.equal(options.method, 'POST');
    if (fail) throw Error('private transport detail must not be rendered');
    return { ...fixture, state: 'granted', uses_left: 1 };
  };
  await w.renderSynastryConsents(root, { apiJson, conversationId: 'conversation/a', isCurrent: () => true });
  assert.equal(w.bad, undefined);
  assert.equal(root.querySelector('img'), null);
  assert(root.textContent.includes('<img'));
  assert.equal(writes.length, 0, 'rendering or chat text never grants consent');
  const button = root.querySelector('button');
  assert.equal(button.type, 'button');
  assert(root.querySelector('[role="status"]'));
  button.click(); button.click();
  assert.equal(button.disabled, true);
  await flush();
  assert.equal(writes.length, 1, 'double click cannot submit a second grant');
  assert.equal(button.disabled, false);
  assert(!root.textContent.includes('private transport'));
  fail = false;
  button.click();
  await flush();
  assert.equal(writes.length, 2);
  assert.deepEqual(writes[0], writes[1], 'uncertain response retry preserves native operation identity');
  assert.deepEqual(Object.keys(writes[0]).sort(), ['confirmed', 'expected_revision', 'request_id']);
  assert.equal(writes[0].confirmed, true);
  assert.equal(root.querySelector('button'), null);
  assert(root.textContent.includes('合盘结果尚未生成'));

  // A delayed response from another owner/conversation cannot revive the old card.
  let resolve;
  let current = true;
  const pending = w.renderSynastryConsents(root, {
    apiJson: () => new Promise(done => { resolve = done; }), conversationId: 'old', isCurrent: () => current
  });
  assert.equal(root.children.length, 0);
  current = false;
  resolve([fixture]);
  await pending;
  assert.equal(root.children.length, 0);
  await w.renderSynastryConsents(root, {
    apiJson: async () => [{ ...fixture, state: 'expired' }, { ...fixture, revision: true }],
    conversationId: 'new', isCurrent: () => true
  });
  assert.equal(root.querySelector('button'), null);
  await w.renderSynastryConsents(root, {
    apiJson: async () => [{ ...fixture, state: 'granted', uses_left: 1 }],
    conversationId: 'new', isCurrent: () => true
  });
  assert.equal(root.querySelector('button'), null, 'already granted cards never resubmit');
  assert(root.textContent.includes('已确认本次使用'));
  console.log('Synastry consent DOM: passed (explicit click, stable retry, XSS and stale identity)');
})().catch(error => { console.error(error); process.exitCode = 1; });
