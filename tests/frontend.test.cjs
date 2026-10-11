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
