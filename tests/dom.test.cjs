const fs=require('fs'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {JSDOM}=require('jsdom');
const html=fs.readFileSync('static/index.html','utf8');
const dom=new JSDOM(html,{url:'https://fixture.invalid/#/chart',runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window;w.HTMLCanvasElement.prototype.getContext=()=>({});
// Handcrafted rendering fixtures have no identity, birth input or copied private data.
const fixtures=JSON.parse(fs.readFileSync('tests/fixtures/demo-charts.json','utf8'));
assert.equal(fixtures.provenance.kind,'synthetic-rendering-fixture');
let history=[],sent=[],memory=[{id:'m1',text:'我喜欢具体的依据',quote:'我喜欢具体的依据',category:'偏好',source_turn:'fixture',created_at:'2026-09-28',status:'active',revision:2}];
let cases=[{id:'case1',title:'学习安排',goal:'安排一个可持续的学习节奏',status:'open',revision:2}],caseEvents=[],tarotDraws=[],tarotCalls=[],memoryEdits=[],stateRevision=2,readingFailure=false,readingResponseLost=false,createNetworkFailure=false;
const tarotIds=fs.readdirSync('static/tarot').filter(n=>/^(major|wands|cups|swords|pentacles)-\d+\.svg$/.test(n)).map(n=>n.slice(0,-4));
assert.equal(tarotIds.length,78);
const tarotDeck={version:'fixture',cards:tarotIds.map(id=>({card_id:id,name:({'major-00':'愚人','major-01':'魔术师','major-02':'女祭司'})[id] || id,upright:'认真观察眼前的条件。',reversed:'留意尚未处理的阻碍。',misreading:'这不是结果保证。',question:'你可以核实什么？'})),spreads:[{id:'focus1',name:'关注点',positions:['此刻值得留意的角度']},{id:'reflect3',name:'梳理问题',positions:['当前处境的反思','可能忽视的因素','可尝试的行动']},{id:'choice5',name:'A/B 选择',positions:['核心诉求','A 的机会提示','A 需核查的顾虑','B 的机会提示','B 需核查的顾虑']}]};
const drawRequests=new Map(),readingVersions=new Map();
const viewDraw=d=>({...d,cards:d.cards.map(c=>c.revealed?{...c,card:tarotDeck.cards.find(x=>x.card_id===c.card_id)}:{position:c.position,label:c.label,back_id:c.back_id,revealed:false})});
const reports=[{type:'晨报',date:'2026-09-28',content:'# 今日报告\n\n专注学习<script>window.pwned=1</script><img src=x onerror="window.pwned=2">'},{type:'周报',date:'2026-09-27',content:'回顾这周的变化'}];
const turn={
 answer:'## 观察与建议\n\n先完成一个小步骤。',
 professional_appendix:'月令与十神需要结合整体判断。<script>window.pwned=4</script><img src=x onerror="window.pwned=5">',
 synthesis:[{theme:'学习安排',relationship:'mixed',interpretation:'先观察真实的学习节奏，再比较不同解释。',contributions:[
  {engine:'bazi',status:'used',reason:'作为整理节奏的象征角度。',evidence:[{ref:'chart:bazi:2026-09-29',path:'/pillars/month',value:'甲申'}]},
  {engine:'ziwei',status:'not_relevant',reason:'这次问题没有明确相关的宫位线索。',evidence:[]},
  {engine:'astro',status:'unavailable',reason:'本次计算资料暂不可用。',evidence:[]}
 ]}],
 evidence:[{ref:'chart:bazi:2026-09-29',claim:'月柱参与本次对照 <x onmouseover="window.pwned=6">',path:'/pillars/month',value:'甲申',source:'chart',data:'测试'}, {ref:'fixture',claim:'用户原话',source:'memory',data:'测试'}],
 caveats:['只把象征解释作为反思线索。'],actions:[],memory_changes:[],meta:{workflow:'decision'}
};
// Synthetic content rendered by the actual Python server renderer; no model or fake API success is implied.
const serverTarotResult=JSON.parse(execFileSync('python',['-c',"import sys,json;sys.path.insert(0,'hermes');from guidance import render_answer;d=json.load(sys.stdin);d['answer']=render_answer(d);print(json.dumps(d,ensure_ascii=False))"],{encoding:'utf8',input:JSON.stringify({plain_summary:'先核实课程时间，再决定是否调整。',explanation:'把已经确认的条件与猜测分开。',reality_context:[{kind:'known',statement:'已确认周三有课程。',ref:'message:synthetic'},{kind:'preference',statement:'希望保留休息时间。',ref:'fact:synthetic'},{kind:'assumption',statement:'假设新安排不会增加通勤。',ref:''},{kind:'missing',statement:'还不知道课程退改规则。',ref:''}],card_interpretations:[{position:3,card_id:'major-02',orientation:'reversed',theme:'审视信息',interpretation:'第三张提醒你先核对条件。',question:'哪些信息仍需确认？'}],tarot_synthesis:['两个角度存在张力，不必强行统一。'],decision_options:[{option:'A：保留安排',benefit:'保持熟悉的节奏',cost:'需要协调休息',risk:'仍可能感到疲惫',reversibility:'退改条件未知',first_step:'先问清调整规则'},{option:'B：暂缓决定',benefit:'留出确认信息的时间',cost:'需要等待',risk:'名额是否保留未知',reversibility:'等待期可调整',first_step:'确认截止时间'}],actions:['核实课程退改规则。'],follow_up:'确认后可以回来补充。',professional_appendix:'象征解释不能代替现实核查。',evidence:[{ref:'message:synthetic',claim:'用户确认课程安排',source:'user_message',data:'已确认周三有课程。'}],synthesis:[{theme:'信息不足时的判断',relationship:'divergent',interpretation:'保留不同角度。',contributions:[{engine:'tarot',status:'uncertain',reason:'只用于提出待核查问题。',evidence:[]}]}],coverage:[{engine:'tarot',status:'used',reason:'使用这次固定牌阵。',evidence:[]},{engine:'bazi',status:'notused',reason:'这次没有请求命盘对照。',evidence:[]}],caveats:[]})}));
const reply=(x,status=200)=>({ok:status<400,status,json:async()=>JSON.parse(JSON.stringify(x))});
const stream=events=>{const bytes=new TextEncoder().encode(events.map(e=>'data: '+JSON.stringify(e)+'\n\n').join('')+'data: [DONE]\n\n');let step=0;return {ok:true,status:200,body:{getReader:()=>({read:async()=>step++===0?{value:bytes.slice(0,13),done:false}:step===2?{value:bytes.slice(13),done:false}:{done:true}})}};};
w.fetch=async(path,options={})=>{
 const u=new URL(path,w.location.origin);
 if(u.pathname==='/api/tarot/deck')return reply(tarotDeck);
 if(u.pathname==='/api/tarot/draws'){
  if(options.method!=='POST')return reply(tarotDraws.map(viewDraw));
  const body=JSON.parse(options.body);tarotCalls.push({operation:'create',body});
  let draw=drawRequests.get(body.idempotency_key);
  if(!draw){const spread=tarotDeck.spreads.find(s=>s.id===body.spread_id),id='draw'+(tarotDraws.length+1);draw={id,spread,question:body.question,background:body.background,options:body.options,case_id:body.case_id || 'case1',draw_source:body.draw_source,reversals:body.reversals,status:body.draw_source==='pick'?'selecting':'pending_reveal',revision:1,created_at:'2026-10-10T12:00:00',backs:body.draw_source==='pick'?Array.from({length:78},(_,i)=>({back_id:'opaque-'+i})):[],cards:body.draw_source==='pick'?[]:spread.positions.map((label,i)=>({position:i+1,label,back_id:'opaque-'+i,revealed:false,card_id:body.manual_cards?.[i].card_id || ['major-00','major-01','major-02','major-03','major-04'][i],orientation:body.manual_cards?.[i].orientation || (body.reversals&&i===1?'reversed':'upright')}))};tarotDraws.push(draw);drawRequests.set(body.idempotency_key,draw);}
  if(createNetworkFailure){createNetworkFailure=false;throw Error('fixture network interrupted after save');}
  return reply({draw:viewDraw(draw),created:true,reused:false});
 }
 const tarotPath=/^\/api\/tarot\/draws\/([^/]+)(?:\/(.*))?$/.exec(u.pathname);
 if(tarotPath){
  const draw=tarotDraws.find(d=>d.id===tarotPath[1]),action=tarotPath[2],body=options.body?JSON.parse(options.body):{};
  if(!draw)return reply({detail:'记录不存在'},404);
  if(options.method==='DELETE'){tarotDraws=tarotDraws.filter(d=>d!==draw);return reply({deleted:true,deleted_ids:[draw.id]});}
  if(!action)return reply(viewDraw(draw));
  if(action==='readings'){
   if(options.method!=='POST')return reply(readingVersions.get(draw.id) || []);
   tarotCalls.push({operation:'reading',draw_id:draw.id,body});
   const rows=readingVersions.get(draw.id) || [],reading_id='reading-'+draw.id+'-'+(rows.length+1),result={...serverTarotResult,card_interpretations:draw.cards.map(c=>({...c,theme:'观察条件',interpretation:'结合实际安排核实。',question:'有什么低成本试验？'}))};
    const error=readingFailure==='unconfigured'?'AI 服务未配置':readingFailure?'AI 服务超时':'';
    rows.push({id:reading_id,request_id:body.request_id,status:readingFailure==='unconfigured'?'unconfigured':readingFailure?'failed':'success',version:rows.length+1,result:readingFailure?null:result,error});readingVersions.set(draw.id,rows);
    if(readingResponseLost){readingResponseLost=false;throw Error('fixture lost after successful reading');}
    return stream([{type:'started',reading_id},{type:'status',text:'正在整理实际牌面'},readingFailure?{type:'error',message:error}:{type:'result',result,reading_id,draw_id:draw.id}]);
  }
  tarotCalls.push({operation:action,draw_id:draw.id,body});
  if(action==='select' && !draw.cards.some(c=>c.back_id===body.back_id)){const i=draw.cards.length;draw.cards.push({position:i+1,label:draw.spread.positions[i],back_id:body.back_id,revealed:false,card_id:['major-00','major-01','major-02'][i],orientation:'upright'});}
  if(action==='reveal')draw.cards.forEach(c=>{if(body.position===undefined || c.position===body.position)c.revealed=true;});
  if(action==='cancel')draw.status='cancelled';
  if(action==='manual'){const updated={...draw,id:draw.id+'revision',revision:draw.revision+1,cards:body.cards.map((c,i)=>({...c,position:i+1,label:draw.spread.positions[i],back_id:'manual-'+i,revealed:false}))};tarotDraws.push(updated);return reply(viewDraw(updated));}
  return reply(viewDraw(draw));
 }
 if(u.pathname==='/api/cases'){
  if(options.method==='POST'){const body=JSON.parse(options.body),entry={id:'case'+(cases.length+1),title:body.title,goal:body.goal,status:'open',revision:3};cases.push(entry);return reply(entry);}
  return reply(cases);
 }
  if(/^\/api\/cases\/[^/]+\/events$/.test(u.pathname)){const body=JSON.parse(options.body);if(body.expected_revision!==stateRevision)return reply({detail:'fixture stale context'},409);caseEvents.push(body);return reply({ok:true});}
 if(/^\/api\/cases\/[^/]+$/.test(u.pathname) && options.method==='PATCH'){const body=JSON.parse(options.body),entry=cases.find(c=>c.id===u.pathname.split('/').at(-1));Object.assign(entry,body.changes);return reply(entry);}
 if(u.pathname==='/api/chat'){
  sent.push(JSON.parse(options.body));
  const text='data: '+JSON.stringify({type:'status',text:'检查依据'})+'\n\ndata: '+JSON.stringify({type:'result',result:turn})+'\n\ndata: [DONE]\n\n';
  const bytes=new TextEncoder().encode(text);let step=0;
  return {ok:true,status:200,body:{getReader:()=>({read:async()=>step++===0?{value:bytes.slice(0,11),done:false}:step===2?{value:bytes.slice(11),done:false}:{done:true}})}};
 }
  if(u.pathname==='/api/memories/m1' && options.method==='PATCH'){const body=JSON.parse(options.body);memoryEdits.push(body);Object.assign(memory[0],body);return reply({ok:true});}
 if(u.pathname==='/api/memories/m1' && options.method==='DELETE'){memory=[];return reply({ok:true});}
 return reply({
  '/api/health':{ok:true},'/api/sessions':[{id:'shared',title:'与明镜对话'},{id:'other',title:'另一段对话'}],
  '/api/history':history,'/api/archive':u.searchParams.get('section')==='reports'?reports:{charts:{bazi:fixtures.bazi.data}},
  '/api/chart':fixtures.bazi.data,'/api/chart_ziwei':fixtures.ziwei.data,'/api/chart_astro':fixtures.astro.data,
   '/api/memories':memory,'/api/memories/m1/audit':[{at:'2026-09-28',operation:'updated',revision:2}],'/api/memories/m1/source':{sources:[{role:'user',at:'2026-09-28',content:'我喜欢具体的依据'}]},'/api/state':{revision:stateRevision,cases,facts:memory},
  '/api/timeline':{forecasts:[],stats:{}},'/api/graph':{},'/api/reports/status':{rows:[]},'/api/search':[]
 }[u.pathname] || {});
};
w.TextDecoder=TextDecoder;w.TextEncoder=TextEncoder;w.localStorage.setItem('mjt_token','fixture-token');
w.ResizeObserver=class{observe(){}disconnect(){}};
w.eval(fs.readFileSync('static/vendor/marked.js','utf8'));
w.eval(fs.readFileSync('static/vendor/purify.js','utf8'));
const appCode=fs.readFileSync('static/app.js','utf8');
const functions=[...appCode.matchAll(/^(?:async )?function (\w+)/gm)].map(m=>m[1]);
w.eval(appCode+'\nObject.assign(window,{'+functions.join(',')+'});');
const tick=()=>new Promise(r=>setTimeout(r,20));
(async()=>{
 await tick();assert.equal(w.document.querySelector('#page-chart').classList.contains('hidden'),false);assert.match(w.document.querySelector('#pageTitle').textContent,/彼此关联/);
 const attack="');window.pwned=3;//\"<x>";const holder=w.document.createElement('div');holder.innerHTML=w.aiAskBtn(attack);
 let captured='';new Function('askAiAbout',holder.querySelector('button').getAttribute('onclick'))(value=>{captured=value;});assert.equal(captured,attack);assert.equal(w.pwned,undefined);
 for(const page of ['chat','chart','tarot','timeline','graph','dict','reports','memory']){
   w.switchPage(page);await tick();assert.equal(w.location.hash,'#/'+page);assert.equal(w.document.querySelector('#page-'+page).classList.contains('hidden'),false);
 }
 w.switchPage('reports');await w.loadReports();
 assert.equal(w.document.querySelectorAll('.report-card').length,2);assert.equal(w.document.querySelector('.report-body script'),null);assert.equal(w.document.querySelector('.report-body img'),null);assert.equal(w.pwned,undefined);
 w.document.querySelector('#reportKind').value='晨报';w.document.querySelector('#reportKind').dispatchEvent(new w.Event('change'));assert.equal(w.document.querySelectorAll('.report-card').length,1);
 const head=w.document.querySelector('.report-head');head.click();assert(w.document.querySelector('.report-body').classList.contains('hidden'));head.click();assert(!w.document.querySelector('.report-body').classList.contains('hidden'));
 w.switchPage('memory');await w.loadMemories();w.document.querySelector('.toggle-memory').click();await tick();assert.equal(memory[0].status,'hidden');assert.equal(w.document.querySelector('.toggle-memory'),null);assert.match(w.document.querySelector('.memory-card').textContent,/新原话确认/);
 w.switchPage('chat');await w.sendChat('测试 SSE 分块消息');assert.equal(sent.length,1);assert.match(w.document.querySelector('#chatFlow').textContent,/先完成一个小步骤/);assert.equal(w.document.querySelector('#sendBtn').disabled,false);
 const body=w.document.querySelector('#chatFlow .msg-ai .msg-body');
 assert.equal(body.firstElementChild.className,'answer-reading');assert.match(body.firstElementChild.textContent,/先完成一个小步骤/);
 assert.doesNotMatch(body.firstElementChild.textContent,/月令|三盘|pillars|chart:bazi/);
 const details=body.querySelector(':scope > .answer-sources');assert(details);assert.equal(details.open,false);assert.equal(body.lastElementChild,details);
 assert.equal(body.querySelectorAll(':scope > .answer-sources').length,1);assert.equal(details.querySelectorAll('.synthesis-contribution').length,3);
 assert.match(details.textContent,/八字/);assert.match(details.textContent,/紫微斗数/);assert.match(details.textContent,/西方星盘/);assert.match(details.textContent,/与此问题关联较弱/);assert.match(details.textContent,/暂无可用资料/);
 assert(details.querySelector('.source-record pre').textContent.includes('/pillars/month'));assert.equal(details.querySelector('.answer-details-body').lastElementChild.className,'answer-detail-section professional-appendix');
 assert.equal(body.querySelector('script,img,x'),null);assert.equal(w.pwned,undefined);details.querySelector('summary').click();assert.equal(details.open,true);
 history=[{role:'assistant',source:'web',at:'2026-09-29T09:00:00',content:turn.answer,context_meta:turn},{role:'assistant',source:'feishu',at:'2026-09-29T09:01:00',content:'旧版记录仍然可读。',context_meta:{evidence:[{ref:'legacy',claim:'历史引用',source:'report',data:'旧报告'}]}}];
 await w.loadHistory();const restored=w.document.querySelectorAll('#chatFlow .msg-ai .msg-body');assert.equal(restored.length,2);const expected=w.document.createElement('div');expected.innerHTML=w.answerHtml(turn,turn.answer);assert.equal(restored[0].innerHTML,expected.innerHTML);assert.equal(restored[0].querySelector('.answer-sources').open,false);
 assert.match(restored[1].querySelector('.answer-reading').textContent,/旧版记录仍然可读/);assert.match(restored[1].querySelector('.answer-sources').textContent,/历史引用/);assert.equal(restored[1].querySelector('.professional-appendix'),null);
 const legacy=w.document.createElement('div');legacy.innerHTML=w.answerHtml(null,'没有额外资料的旧消息。');assert.match(legacy.textContent,/没有额外资料的旧消息/);assert.equal(legacy.querySelector('details'),null);
 // The actual server's answer already includes option tradeoffs; structured context and tarot detail must survive every view.
 const structured=w.document.createElement('div');structured.innerHTML=w.answerHtml(serverTarotResult);
 assert.match(structured.querySelector('.answer-reading').textContent,/A：保留安排/);assert.match(structured.querySelector('.answer-reading').textContent,/B：暂缓决定/);assert.equal(structured.querySelector('.answer-reading').textContent.split('A：保留安排').length,2);
 assert.equal(structured.querySelectorAll('.reality-group').length,4);assert.match(structured.querySelector('.reality-known').textContent,/已知现实/);assert.match(structured.querySelector('.reality-assumption').textContent,/仍是假设/);assert.doesNotMatch(structured.querySelector('.answer-reading').textContent,/message:synthetic|fact:synthetic|审视信息/);
 assert.equal(structured.querySelectorAll(':scope > .answer-sources').length,1);assert.equal(structured.querySelector('.answer-sources').open,false);assert.match(structured.querySelector('.tarot-card-interpretation h3').textContent,/第 3 张/);assert.match(structured.querySelector('.tarot-relations').textContent,/不必强行统一/);assert.match(structured.querySelector('.answer-coverage').textContent,/本次未使用/);assert.match(structured.querySelector('.synthesis-contribution').textContent,/塔罗.*仍不确定/s);assert.equal(structured.querySelector('.answer-details-body').lastElementChild.className,'answer-detail-section professional-appendix');
 const relationOnly=w.document.createElement('div');relationOnly.innerHTML=w.answerHtml({...serverTarotResult,card_interpretations:[]});assert.match(relationOnly.querySelector('.tarot-relations').textContent,/存在张力/);
 history=[{role:'assistant',source:'web',at:'2026-10-10T09:00:00',content:serverTarotResult.answer,context_meta:serverTarotResult}];await w.loadHistory();assert.equal(w.document.querySelector('#chatFlow .msg-ai .msg-body').innerHTML,structured.innerHTML);
 // A saved draw survives a lost response; neither retry nor reading calls redraw it.
 w.switchPage('tarot');await w.loadTarot();const $=s=>w.document.querySelector(s);assert.equal($('#tarotSpread').value,'reflect3');assert.equal($('#tarotAdvanced').open,false);
 $('#tarotQuestion').value='怎样调整当前学习节奏？';createNetworkFailure=true;await w.submitTarot();assert.equal(tarotDraws.length,1);assert.match($('#tarotStatus').textContent,/同一个请求/);await w.submitTarot();
 assert.equal(tarotDraws.length,1);assert.equal(tarotCalls.filter(c=>c.operation==='create')[0].body.idempotency_key,tarotCalls.filter(c=>c.operation==='create')[1].body.idempotency_key);
 assert.equal(w.document.querySelectorAll('#tarotDrawRoot .tarot-position').length,3);assert.equal($('#tarotDrawRoot .tarot-card img').getAttribute('src'),'/static/tarot/back.svg');assert(!$('#tarotDrawRoot').innerHTML.includes('major-00'));
 $('[data-reveal-all]').click();await tick();assert.equal(w.document.querySelectorAll('#tarotDrawRoot .tarot-card.revealed').length,3);assert.equal(w.document.querySelectorAll('#tarotDrawRoot .tarot-card.no-motion').length,3);assert.match($('#tarotDrawRoot').textContent,/逆位/);assert.match($('#tarotDrawRoot').textContent,/你可以核实什么/);
 const fixedCards=tarotDraws[0].cards.map(c=>c.card_id+':'+c.orientation);await w.requestTarotReading();assert.match($('#tarotReadingRoot').textContent,/先核实课程时间/);assert.equal($('#tarotReadingRoot .answer-sources').open,false);assert.equal(w.document.querySelectorAll('#tarotReadingRoot .tarot-reading > .answer-sources').length,1);assert.equal(w.document.querySelectorAll('#tarotReadingRoot .reality-group').length,4);assert.equal(w.document.querySelectorAll('#tarotReadingRoot .tarot-card-interpretation').length,3);await w.openTarotDraw('draw1');assert.match($('#tarotReadingRoot').textContent,/先核实课程时间/);assert.doesNotMatch($('#tarotReadingRoot').textContent,/尚未成功/);readingResponseLost=true;await w.requestTarotReading('新增已经核实的背景');assert.match($('#tarotReadingStatus').textContent,/找回并保存/);
 readingFailure=true;await w.requestTarotReading('课程安排已变化');assert.match($('#tarotReadingStatus').textContent,/AI 服务超时/);assert.equal(tarotDraws.length,1);assert.deepEqual(tarotDraws[0].cards.map(c=>c.card_id+':'+c.orientation),fixedCards);
 readingFailure=false;await w.requestTarotReading('课程安排已变化');assert.equal(tarotDraws.length,1);assert.equal(tarotCalls.filter(c=>c.operation==='reading').at(-1).draw_id,'draw1');assert.notEqual(tarotCalls.filter(c=>c.operation==='reading').at(-1).body.request_id,tarotCalls.filter(c=>c.operation==='reading').at(-2).body.request_id);
 $('[data-tarot-chat]').click();assert.equal(w.location.hash,'#/chat');await w.sendChat('第三张是什么意思？');assert.equal(sent.at(-1).draw_id,'draw1');assert.equal(sent.at(-1).case_id,'case1');
 await w.openTarotDraw('draw1');assert(w.location.hash.includes('draw=draw1'));assert.match($('#tarotReadingRoot').textContent,/先核实课程时间/);$('#tarotFeedback').value='我已经与老师确认下周减少一门课';$('#tarotFeedbackKind').value='decided';await w.saveTarotFeedback({preventDefault(){}});assert.equal(caseEvents.at(-1).kind,'decided');assert.equal(caseEvents.at(-1).expected_revision,2);assert.match($('#tarotFeedbackStatus').textContent,/已保存/);await w.openTarotFeedback();stateRevision=3;$('#tarotFeedback').value='我已经完成第一步';const savedCount=caseEvents.length;await w.saveTarotFeedback({preventDefault(){}});assert.equal(caseEvents.length,savedCount);assert.match($('#tarotFeedbackStatus').textContent,/填写期间有更新/);assert.equal($('#tarotFeedback').value,'我已经完成第一步');await w.saveTarotFeedback({preventDefault(){}});assert.equal(caseEvents.length,savedCount);stateRevision=2;
 // Pick mode sends only opaque backs and keeps keyboard movement available.
 w.newTarotQuestion(false);$('#tarotQuestion').value='如何安排休息？';$('#tarotSource').value='pick';w.updateTarotSettings();await w.submitTarot();assert.equal(w.document.querySelectorAll('[data-select-back]').length,78);assert(!$('#tarotDrawRoot').innerHTML.includes('major-00'));
 $('[data-tarot-chat]').click();await w.sendChat('先聊聊现实安排');assert.equal(sent.at(-1).draw_id,undefined);assert.equal(sent.at(-1).case_id,'case1');await w.openTarotDraw(tarotDraws[1].id);
 const backs=w.document.querySelectorAll('[data-select-back]');backs[0].focus();backs[0].dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));assert.equal(w.document.activeElement,backs[1]);
 await Promise.all([w.mutateTarotDraw('select',{back_id:'opaque-4'}),w.mutateTarotDraw('select',{back_id:'opaque-4'})]);assert.equal(tarotDraws[1].cards.length,1);await w.mutateTarotDraw('select',{back_id:'opaque-7'});await w.mutateTarotDraw('select',{back_id:'opaque-12'});assert.equal(tarotDraws[1].cards.length,3);assert.equal(tarotCalls.filter(c=>c.operation==='select'&&c.body.back_id==='opaque-4').length,1);await w.mutateTarotDraw('reveal',{});
 readingFailure='unconfigured';await w.requestTarotReading();assert.match($('#tarotReadingRoot').textContent,/未配置/);assert.match($('#tarotReadingRoot').textContent,/静态牌意/);assert.equal($('#tarotReadingRoot .tarot-reading'),null);readingFailure=false;
 // A/B cannot freeze undefined options; manual mode accepts explicit physical cards.
 w.newTarotQuestion(false);$('#tarotQuestion').value='在两个安排之间如何比较？';$('#tarotSpread').value='choice5';w.updateTarotSettings();const beforeAB=tarotDraws.length;await w.submitTarot();assert.equal(tarotDraws.length,beforeAB);assert.match($('#tarotFormError').textContent,/A 与 B/);$('#tarotOptionA').value='保留安排';$('#tarotOptionB').value='减少课程';$('#tarotSource').value='auto';w.updateTarotSettings();await w.submitTarot();assert.equal(tarotDraws.at(-1).cards.length,5);assert.deepEqual(tarotDraws.at(-1).options,{A:'保留安排',B:'减少课程'});
 await w.mutateTarotDraw('reveal',{});const abDraw=tarotDraws.at(-1);$('[data-tarot-chat]').click();await w.sendChat('接着比较 A 与 B');assert.equal(sent.at(-1).draw_id,abDraw.id);assert.equal(sent.at(-1).case_id,abDraw.case_id);await w.openTarotDraw(abDraw.id);assert.match($('.tarot-frozen-options').textContent,/A.*保留安排.*B.*减少课程/s);
 $('#tarotOptionA').value='未保存的另一含义';w.newTarotQuestion(true);assert.equal($('#tarotSpread').value,'choice5');assert.equal($('#tarotOptionA').value,'保留安排');assert.equal($('#tarotOptionB').value,'减少课程');w.newTarotQuestion(false);assert.equal($('#tarotOptionA').value,'');assert.equal($('#tarotOptionB').value,'');
 w.newTarotQuestion(false);$('#tarotQuestion').value='记录这张实体牌';$('#tarotSpread').value='focus1';$('#tarotSource').value='manual';w.updateTarotSettings();$('#tarotManual [data-manual-card]').value='major-02';$('#tarotManual [data-manual-orientation]').value='reversed';await w.submitTarot();await w.mutateTarotDraw('reveal',{});assert.equal(tarotDraws.at(-1).draw_source,'manual');assert.equal(tarotDraws.at(-1).cards[0].card_id,'major-02');
 w.showTarotCorrection();$('#tarotCorrectionRoot [data-manual-card]').value='major-01';$('#tarotCorrectionReason').value='刚才把实体牌名称录入错了';$('#tarotCorrectionForm').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick();assert(w.location.hash.includes('revision'));assert.equal(tarotDraws.at(-1).cards[0].card_id,'major-01');await w.deleteTarotDraw();assert.equal($('#tarotForm').classList.contains('hidden'),false);
 w.switchPage('memory');await w.loadMemories();await tick();$('.source-memory').click();await tick();assert.match($('.memory-source').textContent,/我喜欢具体的依据/);assert.doesNotMatch($('.memory-source').textContent,/"content"|source_refs/);$('.audit-memory').click();await tick();assert.doesNotMatch($('.memory-audit').textContent,/旧记录/);$('.case-close').click();await tick();assert.equal(cases[0].status,'closed');$('.delete-memory').click();await tick();assert.equal(memory.length,0);
 memory=[{id:'m1',text:'我的出生时区是 8',field:'birth.timezone_offset',value:8,status:'active',revision:1},{id:'deleted-tombstone',text:'',status:'deleted',revision:2}];await w.loadMemories();assert.equal(w.document.querySelectorAll('.memory-card').length,1);const editsBefore=memoryEdits.length;assert.equal($('.memory-field-value').value,'');$('.memory-card textarea').value='我更正出生时区为 9';$('.save-memory').click();await tick();assert.equal(memoryEdits.length,editsBefore);$('.memory-field-value').value='9';$('.save-memory').click();await tick();assert.equal(memoryEdits.length,editsBefore);$('.memory-confirm-field').checked=true;$('.save-memory').click();await tick();assert.equal(memoryEdits.at(-1).value,9);assert.equal(memoryEdits.at(-1).expected_revision,stateRevision);assert.match(memoryEdits.at(-1).text,/9/);
 const retired=w.document.createElement('div');retired.innerHTML=w.readableSource({sources:[{content:'已保留的用户原话',usable_for_context:false}]});assert.match(retired.textContent,/已停止用于后续分析/);assert.match(retired.textContent,/已保留的用户原话/);
 w.setChatContext({case_id:'case1',title:'学习安排'});$('#chatInput').value='继续梳理学习安排';$('#tarotBackground').value='其他事项的旧背景';$('#chatTarotBtn').click();await tick();assert.equal($('#tarotBackground').value,cases[0].goal);assert.equal($('#tarotQuestion').value,'继续梳理学习安排');w.newTarotQuestion(false);w.restoreTarotForm();assert.equal($('#tarotBackground').value,'');assert.equal($('#tarotCaseHint').textContent,'');w.setChatContext({case_id:'case1',draw_id:'draw1'});$('#chatInput').value='';$('#chatTarotBtn').click();await tick();assert(w.location.hash.includes('draw=draw1'));assert.equal($('#tarotForm').classList.contains('hidden'),true);
 assert.match(fs.readFileSync('static/paper.css','utf8'),/@media\(prefers-reduced-motion:reduce\)/);
 w.location.hash='#/chart';w.applyRoute();assert(!w.document.querySelector('#page-chart').classList.contains('hidden'));
 console.log('PASS: eight routes, v5 compatibility, three tarot spreads/sources, private card backs, keyboard, fixed-draw retries, recovery, A/B freeze, manual correction, linked chat, feedback, source and memory controls');dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
