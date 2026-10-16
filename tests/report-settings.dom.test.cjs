const fs=require('fs'),assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync('static/index.html','utf8'),{url:'https://fixture.invalid/#/reportsettings',runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window,document=w.document;
w.HTMLCanvasElement.prototype.getContext=()=>({});w.ResizeObserver=class{observe(){}disconnect(){}};
w.TextDecoder=TextDecoder;w.TextEncoder=TextEncoder;w.localStorage.setItem('mjt_token','synthetic-layout-only');
Object.defineProperty(w,'innerWidth',{configurable:true,value:390});
const copy=value=>JSON.parse(JSON.stringify(value));
const base={configured:true,initialized:true,revision:3,enabled:true,status:'active',can_modify:true,delivery_state:{sending:0,uncertain:0,pending:0},timezone:'Asia/Shanghai',next_prepare:'2026-10-11T23:50:00+08:00',next_delivery:'2026-10-12T00:05:00+08:00',preview_prepare:'2026-10-11T23:50:00+08:00',preview_delivery:'2026-10-12T00:05:00+08:00'};
let schedules=[{...base,id:'daily',kind:'daily',label:'晨报',time:'00:05'},
 {...base,id:'weekly',kind:'weekly',label:'周报',time:'22:15',weekday:2,can_modify:false,delivery_state:{sending:1,uncertain:0,pending:0},status_reason:'报告正在发送，当前投递完成后才可修改。'},
 {...base,id:'monthly',kind:'monthly',label:'月报',time:'08:31',day:'last'},
 {...base,id:'quarterly',kind:'quarterly',label:'季报',time:'10:33',day:28,configured:false,enabled:false,status:'unconfigured',can_modify:false,status_reason:'报告渠道尚未配置，不能启用。',next_prepare:null,next_delivery:null}];
let mode='normal',getFailure=false;const requests=[],commits=new Map();
const reply=(value,status=200)=>({ok:status<400,status,json:async()=>copy(value)});
w.fetch=async(path,options={})=>{
 const url=new URL(path,'https://fixture.invalid');
 if(url.pathname==='/api/reports/schedules'){
  if(options.method!=='PATCH'){
   if(getFailure){getFailure=false;throw Error('synthetic GET interrupted');}
   return reply({timezone:'Asia/Shanghai',prepare_minutes:15,schedules});
  }
  const body=JSON.parse(options.body);requests.push(copy(body));
  const row=schedules.find(item=>item.kind===body.kind);
  if(commits.has(body.request_id))return reply(commits.get(body.request_id));
  if(mode==='conflict'){
   mode='normal';row.revision++;row.time='09:19';return reply({detail:'配置版本冲突'},409);
  }
  if(body.expected_revision!==row.revision)return reply({detail:'配置版本冲突'},409);
  const result={...row,...body,revision:row.revision+1,status:body.enabled?'active':'paused',next_prepare:'2026-10-12T00:47:00+08:00',next_delivery:'2026-10-12T01:02:00+08:00'};
  delete result.expected_revision;delete result.request_id;
  Object.assign(row,result);result.receipt={id:row.kind,kind:'report_schedule',revision:row.revision,write_status:'saved'};commits.set(body.request_id,result);
  if(mode==='lost-reply'){mode='normal';throw Error('synthetic reply lost after committed save');}
  if(mode==='invalid-receipt'){mode='normal';return reply({...result,receipt:{id:row.kind,kind:'report_schedule',revision:row.revision,write_status:'rejected'}});}
  return reply(result);
 }
 if(['/api/history','/api/sessions','/api/cases','/api/memories','/api/reports'].includes(url.pathname))return reply([]);
 return reply({});
};
w.eval(fs.readFileSync('static/vendor/marked.js','utf8'));w.eval(fs.readFileSync('static/vendor/purify.js','utf8'));
const app=fs.readFileSync('static/app.js','utf8'),functions=[...app.matchAll(/^(?:async )?function (\w+)/gm)].map(match=>match[1]);
w.eval(app+'\nObject.assign(window,{'+functions.join(',')+'});');
const tick=()=>new Promise(resolve=>setTimeout(resolve,20)),find=selector=>document.querySelector(selector);
const form=kind=>find('#report-'+kind+'-form');
const change=(selector,value)=>{const field=find(selector);if(field.type==='checkbox')field.checked=value;else field.value=value;field.dispatchEvent(new w.Event('input',{bubbles:true}));};
const submit=kind=>form(kind).dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
(async()=>{
 await tick();await w.loadReportSettings();
 assert.equal(document.querySelectorAll('.schedule-card').length,4);
 assert.equal(find('#page-reportsettings').classList.contains('hidden'),false);
 assert.equal(document.querySelectorAll('[data-page="reportsettings"]').length,2);
 assert.equal(find('#report-daily-time').value,'00:05');assert.equal(find('#report-weekly-weekday').value,'2');
 assert.equal(find('#report-monthly-day').value,'last');assert.equal(find('#report-quarterly-day').value,'28');
 assert.equal(find('#report-monthly-day').options.length,29);
 assert.match(form('daily').textContent,/2026\/10\/11 23:50/);assert.match(form('daily').textContent,/2026\/10\/12 00:05/);
 assert.match(find('.schedule-intro').textContent,/北京时间.*15 分钟/);
 assert.match(form('quarterly').textContent,/1、4、7、10 月/);
 for(const control of document.querySelectorAll('.schedule-card input,.schedule-card select'))assert.equal(control.labels.length,1,'Each actual control has one accessible label');
 assert.equal(document.querySelector('.schedule-card input[name="target"]'),null);
 assert.equal(find('#report-quarterly-enabled').disabled,true);assert.equal(form('quarterly').querySelector('.schedule-save').disabled,true);
 assert.equal(find('#report-weekly-time').disabled,true);assert.match(form('weekly').querySelector('.schedule-state').textContent,/发送中/);
 const before=requests.length;submit('weekly');submit('quarterly');await tick();assert.equal(requests.length,before);
 w.switchPage('reports');await tick();find('#openReportSettingsBtn').click();assert.equal(w.location.hash,'#/reportsettings');assert.equal(document.activeElement,find('#pageTitle'));
 // Native required time validation blocks empty submissions, without clearing the draft.
 change('#report-daily-time','');submit('daily');await tick();assert.equal(requests.length,before);assert.equal(find('#report-daily-time').value,'');
 // A committed save with a lost response retains its request ID and draft on retry.
 change('#report-daily-time','01:02');mode='lost-reply';submit('daily');await tick();
 assert.match(form('daily').querySelector('[role="status"]').textContent,/尚未确认保存.*草稿仍保留/);
 assert.equal(find('#report-daily-time').value,'01:02');assert.equal(document.activeElement,form('daily').querySelector('.schedule-save'));
 assert.doesNotMatch(form('daily').querySelector('[role="status"]').textContent,/已保存/);
 submit('daily');await tick();const first=requests.at(-2),retry=requests.at(-1);assert.equal(first.request_id,retry.request_id);assert.equal(first.expected_revision,3);
 assert.deepEqual(Object.keys(first).sort(),['enabled','expected_revision','kind','request_id','time']);
 assert.match(form('daily').querySelector('[role="status"]').textContent,/已保存晨报设置，版本 4/);
 assert.match(form('daily').textContent,/2026\/10\/12 00:47/);
 // A 409 never replaces user edits, never blind-resubmits, and focuses an explicit refresh.
 change('#report-monthly-time','14:29');change('#report-monthly-day','13');mode='conflict';submit('monthly');await tick();
 const conflictRequest=requests.at(-1);assert.equal(find('#report-monthly-time').value,'14:29');assert.equal(find('#report-monthly-day').value,'13');
 assert.equal(form('monthly').querySelector('.schedule-save').disabled,true);assert.equal(document.activeElement,form('monthly').querySelector('.schedule-refresh'));
 const afterConflict=requests.length;submit('monthly');await tick();assert.equal(requests.length,afterConflict);
 getFailure=true;form('monthly').querySelector('.schedule-refresh').click();await tick();assert.match(form('monthly').querySelector('[role="status"]').textContent,/读取失败.*草稿仍保留/);assert.equal(find('#report-monthly-time').value,'14:29');assert.equal(document.activeElement,form('monthly').querySelector('.schedule-refresh'));
 form('monthly').querySelector('.schedule-refresh').click();await tick();assert.equal(find('#report-monthly-time').value,'14:29');assert.equal(find('#report-monthly-day').value,'13');
 assert.match(form('monthly').querySelector('[role="status"]').textContent,/核对后重新保存/);assert.equal(form('monthly').querySelector('.schedule-save').disabled,false);
 assert.equal(document.activeElement,form('monthly').querySelector('.schedule-save'));submit('monthly');await tick();
 assert.equal(requests.at(-1).expected_revision,4);assert.notEqual(requests.at(-1).request_id,conflictRequest.request_id);assert.equal(requests.at(-1).day,13);
 assert(!('weekday' in requests.at(-1)));assert.match(form('monthly').querySelector('[role="status"]').textContent,/已保存月报设置/);
 // A malformed receipt cannot produce a successful UI save.
 change('#report-daily-time','02:03');mode='invalid-receipt';submit('daily');await tick();assert.equal(find('#report-daily-time').value,'02:03');assert.match(form('daily').querySelector('[role="status"]').textContent,/尚未确认保存/);
 const invalidRequest=requests.at(-1);submit('daily');await tick();assert.equal(requests.at(-1).request_id,invalidRequest.request_id);assert.match(form('daily').querySelector('[role="status"]').textContent,/已保存/);
 // Navigation and failed rereads preserve the same unfinished draft.
 change('#report-daily-time','03:04');w.switchPage('chat');w.switchPage('reportsettings');await tick();assert.equal(find('#report-daily-time').value,'03:04');getFailure=true;await w.loadReportSettings();assert.equal(find('#report-daily-time').value,'03:04');
 // An initialized binding with no schedule can be explicitly saved at revision zero.
 const weekly=schedules.find(row=>row.kind==='weekly');Object.assign(weekly,{initialized:false,revision:0,status:'uninitialized',can_modify:true,delivery_state:{sending:0,uncertain:0,pending:0},status_reason:''});
 await w.loadReportSettings();assert.equal(find('#report-weekly-enabled').disabled,false);change('#report-weekly-weekday','1');change('#report-weekly-time','18:22');submit('weekly');await tick();assert.equal(requests.at(-1).expected_revision,0);assert.equal(requests.at(-1).weekday,1);assert(!('day' in requests.at(-1)));assert.match(form('weekly').querySelector('[role="status"]').textContent,/已保存周报设置/);
 change('#report-monthly-enabled',false);submit('monthly');await tick();assert.match(form('monthly').querySelector('.schedule-state').textContent,/已暂停/);assert.match(form('monthly').querySelector('.schedule-preview-title').textContent,/启用后的时间预览/);
 console.log('PASS: four API-derived schedules, native labelled inputs, Shanghai previews across midnight, configured/sending locks, receipt-only saves, stable retries, 409 drafts, explicit refresh and focus (JSDOM, 390px setting; no layout engine)');
 dom.window.close();
})().catch(error=>{console.error(error);dom.window.close();process.exitCode=1;});
