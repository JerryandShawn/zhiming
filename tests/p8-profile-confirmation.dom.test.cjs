const fs = require('fs');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const code = fs.readFileSync('static/p8-profile-confirmation.js', 'utf8');
const html = fs.readFileSync('static/index.html', 'utf8');
assert(html.indexOf('/static/p8-profile-confirmation.js') < html.indexOf('/static/app.js'));
const dom = new JSDOM('<main id="root"></main>', { runScripts: 'outside-only' });
const w = dom.window;
w.eval(code + '\nwindow.renderP8ProfileRequirements=renderP8ProfileRequirements;');
const root = w.document.querySelector('#root');
const card = { action: 'open_profile', labels: ['出生地时区', '<img src=x onerror="window.bad=1">'],
  message: '准确排盘还需要核对这些资料。尚未计算。' };
const flush = () => new Promise(resolve => setTimeout(resolve, 0));
(async () => {
  const requests = [];
  let opens = 0, release;
  let current = true;
  await w.renderP8ProfileRequirements(root, {
    apiJson: async (url, options) => { requests.push([url, options]); return [card]; },
    conversationId: 'current', isCurrent: () => current,
    openProfile: () => { opens++; return new Promise(resolve => { release = resolve; }); }
  });
  assert.equal(opens, 0, 'loading native requirements cannot open or submit a form');
  assert.equal(root.querySelectorAll('input').length, 0, 'no inferred birth values or consent checkbox');
  assert.equal(root.querySelector('img'), null, 'labels are plain text');
  const button = root.querySelector('button');
  button.click(); button.click();
  assert.equal(opens, 1, 'only explicit single click navigates to the existing form');
  assert.equal(button.disabled, true);
  release(); await flush();
  assert.equal(button.disabled, false);
  assert.equal(requests.length, 1);
  assert.equal(requests[0][1], undefined, 'the card only performs native discovery GET');
  current = false; button.click();
  assert.equal(opens, 1, 'old identity cannot open the previous card');

  let resolve;
  current = true;
  const pending = w.renderP8ProfileRequirements(root, {
    apiJson: () => new Promise(done => { resolve = done; }), conversationId: 'old',
    isCurrent: () => current, openProfile: () => { opens++; }
  });
  assert.equal(root.children.length, 0);
  current = false; resolve([card]); await pending;
  assert.equal(root.children.length, 0, 'late response cannot revive another conversation');
  await w.renderP8ProfileRequirements(root, {
    apiJson: async () => [], conversationId: 'now', isCurrent: () => true, openProfile: () => { opens++; }
  });
  assert.equal(root.children.length, 0, 'confirmed current profile removes the requirement card');
  await w.renderP8ProfileRequirements(root, {
    apiJson: async () => { throw Error('private transport value'); }, conversationId: 'now',
    isCurrent: () => true, openProfile: () => { opens++; }
  });
  assert(!root.textContent.includes('private transport value'));
  console.log('P8 profile confirmation DOM passed: explicit navigation, no write, XSS, stale identity, refresh');
})().catch(error => { console.error(error); process.exitCode = 1; });
