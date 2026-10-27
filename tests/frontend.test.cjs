const fs=require('fs'), vm=require('vm'), assert=require('node:assert/strict');
const html=fs.readFileSync('static/index.html','utf8');
const code=fs.readFileSync('static/app.js','utf8').split("$('#todayLabel').textContent=")[0];
const elements=new Map();
function element(selector){
  if(!elements.has(selector))elements.set(selector,{value:'',innerHTML:'',textContent:'',style:{},dataset:{},
    classList:{add(){},remove(){},toggle(){},contains(){return false;}},addEventListener(){},
    getContext(){return {};},getBoundingClientRect(){return {width:900,height:600}},querySelectorAll(){return []},
    appendChild(){},focus(){},remove(){},setAttribute(){}});
  return elements.get(selector);
}
const sandbox={console,Intl,Date,Map,Set,URLSearchParams,TextDecoder,
  document:{querySelector:element,querySelectorAll(){return []},addEventListener(){},createElement:element},
  window:{addEventListener(){},devicePixelRatio:1},localStorage:{getItem(){return ''}},sessionStorage:{getItem(){return ''}},
  location:{hash:''},tailwind:{},marked:{setOptions(){},parse:x=>x},DOMPurify:{sanitize:x=>x},
  ResizeObserver:class{observe(){}},requestAnimationFrame:f=>f(),setTimeout:f=>0,clearTimeout(){},
};
vm.createContext(sandbox);vm.runInContext(code,sandbox);
assert.equal(sandbox.fmtHistTime('2026-10-11T13:25:00+00:00'),'10-11 21:25');
assert.equal(sandbox.fmtHistTime('2026-10-11T21:25:00+08:00'),'10-11 21:25');
assert.equal(sandbox.fmtHistTime('2026-10-11T18:05:00Z'),'10-12 02:05');
assert.equal(sandbox.fmtHistTime('2026-10-11T18:55:00+05:30'),'10-11 21:25');
assert.equal(sandbox.fmtHistTime('2026-08-22 11:05:01'),'08-22 11:05');
assert.equal(sandbox.fmtHistTime('2026-99-22T11:05:01Z'),'');
element('#analysisDate').value='2026-09-28';element('#analysisFocus').value='学业与成长';
vm.runInContext(`
ziweiData={horoscope:{daily:{name:'流日',ganzhi:'乙巳',mutagen_links:[{star:'天机',mutagen:'禄',palace_index:4,natal_palace:'官禄',scope_palace:'命宫'}]}}};
astroData={transits:{date:'2026-09-28',aspects_to_natal:[{from:'土星',to:'太阳',aspect:'六合',orb:1.2}]},aspects:[{from:'太阳',to:'月亮',aspect:'拱相',orb:3}]};
`,sandbox);
const zw=sandbox.renderZiweiLinks({index:0,linked_palaces:[{index:4,relation:'三合',name:'官禄',major:[{name:'天机'}]}]});
assert.match(zw,/openPalaceDetail\(4\)/);assert.match(zw,/天机化禄/);
const astro=sandbox.renderAstroLinks('p:太阳');assert.match(astro,/土星/);assert.match(astro,/容许度 1.2/);
vm.runInContext('closeDrawer=()=>{}; switchPage=()=>{}; sendChat=(message,selection)=>{globalThis.sent={message,selection}};',sandbox);
sandbox.askLinked('ziwei',4,'官禄宫');assert.equal(sandbox.sent.selection.key,'4');assert.equal(sandbox.sent.selection.date,'2026-09-28');assert.match(sandbox.sent.message,/学业与成长/);
sandbox.showSlices({chart_status:{bazi:'ok',ziwei:'error',astro:'ok'},history_messages:16,records:12});
assert.match(element('#sliceInfo').innerHTML,/紫微 · 数据不足/);
console.log('PASS: palace navigation, four transformations, transit aspects, structured selection, real context status');

const updatedReceiptHtml=sandbox.memoryUpdateReceiptsHtml({receipts:[{write_status:'updated',summary:'已更新：茶 → 咖啡［撤销］',ids:['change-synthetic']}]});
assert.match(updatedReceiptHtml,/已更新：茶 → 咖啡［撤销］/);
assert.match(updatedReceiptHtml,/role="status"/);
assert.equal(sandbox.memoryUpdateReceiptsHtml({receipts:[{write_status:'saved',summary:'old'}]}),'');
assert.doesNotMatch(sandbox.memoryUpdateReceiptsHtml({receipts:[{write_status:'updated',summary:'<script>bad()</script>'}]}),/<script>/);
assert.match(sandbox.answerHtml({answer:'合成回答',receipts:[{write_status:'updated',summary:'已更新：A → B［撤销］'}]}),/已更新：A → B［撤销］/);
console.log('PASS: updated receipt status is shown and escaped without inventing an undo endpoint');
