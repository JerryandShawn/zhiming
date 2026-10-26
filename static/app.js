"use strict";
/* ================= 基础工具 ================= */
const $  = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const jsArg = value => esc(JSON.stringify(String(value ?? '')));
const operationCache=new Map();
const focusReturns=new Map();
function rememberFocus(name){focusReturns.set(name,document.activeElement);}
function restoreFocus(name){const element=focusReturns.get(name);if(element?.isConnected)element.focus({preventScroll:true});focusReturns.delete(name);}

const DIMS = [
  { k: "爱情",   c: "#E8709C" },
  { k: "事业学业", c: "#5B8DD9", alias: ["事业", "学业"] },
  { k: "金钱",   c: "#997b35" },
  { k: "友情",   c: "#5FA97A" },
  { k: "家庭",   c: "#B08D5B" },
  { k: "健康",   c: "#6BC5B8" }
];
function dimColor(name) {
  if (!name) return "#8B7CF6";
  for (const d of DIMS) {
    if (d.k === name || name.includes(d.k) || d.k.includes(name)) return d.c;
    if ((d.alias || []).some(a => name.includes(a))) return d.c;
  }
  return "#8B7CF6";
}
const WXC = { "金": "#997b35", "木": "#5FA97A", "水": "#5B8DD9", "火": "#D96A5B", "土": "#B08D5B" };
const wxColor = w => WXC[w] || "#9AA1B5";

const md = t => {
  if (window.marked && marked.parse) {
    marked.setOptions({ breaks: true, gfm: true });
    return DOMPurify.sanitize(marked.parse(String(t ?? "")), {ADD_ATTR: ["target"], FORBID_TAGS:["img","iframe","form","style"]});
  }
  return esc(t).replace(/\n/g, "<br>");
};

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 2200);
}

function emptyState(sig, line1, line2) {
  return `<div class="empty-state">
    <div class="sig">${esc(sig)}</div>
    <div class="text-sm text-gray-400">${esc(line1)}</div>
    ${line2 ? `<div class="text-xs mt-2">${esc(line2)}</div>` : ""}
  </div>`;
}
function errState(msg, retryFnName) {
  return `<div class="glass p-6 text-center">
    <div class="err-banner inline-block text-left">${esc(msg)}</div>
    ${retryFnName ? `<div class="mt-4"><button class="btn-gold px-4 py-2 text-sm" onclick="${retryFnName}()">重试</button></div>` : ""}
  </div>`;
}

/* ================= 口令 / 鉴权 ================= */
const TOKEN_KEY = "mjt_token";
const getToken = () => localStorage.getItem(TOKEN_KEY) || "";
function saveToken(v) { localStorage.setItem(TOKEN_KEY, v.trim()); $("#tokenInput").value = v.trim(); }
function openTokenModal(isError) {
  if($('#tokenModal').classList.contains('hidden'))rememberFocus('token');
  $("#tokenModal").classList.remove("hidden");
  $("#tokenErr").classList.toggle("hidden", !isError);
  setTimeout(() => $("#tokenModalInput").focus(), 50);
}
function closeTokenModal() { $("#tokenModal").classList.add("hidden"); $("#tokenErr").classList.add("hidden");restoreFocus('token'); }

async function api(path, opt = {}) {
  const headers = Object.assign({ "X-Token": getToken() }, opt.headers || {});
  if (opt.body) headers["Content-Type"] = "application/json";
  const r = await fetch(path, Object.assign({}, opt, { headers }));
  if (r.status === 401) { openTokenModal(true); const e = new Error("未授权：口令错误或已失效"); e.status = 401; throw e; }
  return r;
}
async function apiJson(path, opt = {}) {
  const r = await api(path, opt);
  if (!r.ok) {
    let detail = "";
    try { const j = await r.json(); detail = j.detail || JSON.stringify(j); } catch { detail = await r.text().catch(() => ""); }
    const e = new Error(detail || ("HTTP " + r.status)); e.status = r.status; throw e;
  }
  return r.json();
}
async function writeJson(path, data={}, method='POST') {
  const operation=method+':'+path, body={...data};
  body.request_id ||= tarotOperationKey(operation,data);
  body.idempotency_key ||= body.request_id;
  const result=await apiJson(path,{method,body:JSON.stringify(body)});
  clearTarotOperation(operation);
  return result;
}
function entityRevision(entry) {
  const value=entry?.revision ?? entry?.context_revision;
  if(!Number.isInteger(value))throw Error('资料版本暂不可用，请刷新后再保存。');
  return value;
}

/* ================= 页签切换 ================= */
const PAGE_META = {
 chat:["把最近的事，慢慢说清楚。","带着经历来，借助依据思考，再回到日常行动。","对话","一事一问 · 一日一观"],
 chart:["从一处细节，看见彼此关联。","选择同一日期，在八字、紫微与星盘间对照；点击元素深入阅读。","命盘","三盘对照 · 有据可查"],
 tarot:["给眼前的问题，留一个新角度。","抽牌是起点；把象征放回现实，整理选择与下一步。","塔罗","同一次抽牌 · 持续讨论"],
 timeline:["回看变化，也留下反馈。","把过去的判断放回真实经历，逐步辨认属于你的规律。","时间轴","观察 · 记录 · 校准"],
 graph:["人与人之间，留下生活的线索。","查看已记录的人物、关系和事件，点击节点读懂其中的联系。","缘网","关系来自档案记录"],
 dict:["让经验，慢慢成为你的词典。","个人解释与样本记录并读；尚无足够反馈的判断，继续保留疑问。","词典","用经历校准语言"],
 reports:["留一段时间，读今天的自己。","报告按日期归档，展开阅读、检索回看，也可以导出留存。","报告","阅读存档 · 查看投递"],
 reportsettings:["为报告，留一个合适的时间。","设置晨报、周报、月报与季报的发送时间，核对下一次准备和投递。","报告设置","北京时间 · 提前准备"],
 cases:["接着上次，把事情慢慢理清。","查看这件事的背景、决定与实际反馈，继续跟进下一步。","我的事项","一件事 · 持续跟进"],
 memory:["记住的信息，由你核对。","查看长期信息与原话来源，随时更正、停用或删除。","已记住的信息","由你确认 · 由你更正"]
};
const loaders = { chat: loadChatScope, chart: loadChart, tarot: loadTarot, cases: loadCases, timeline: loadTimeline, graph: loadGraph, dict: loadDict, reports: loadReports, reportsettings: loadReportSettings, memory: loadMemories };
const loaded = {};
let currentPage = "chat";
function switchPage(name, fromRoute) {
  if (!loaders[name]) name = "chat";
  currentPage = name;
  const heading = PAGE_META[name];
  $("#pageTitle").textContent=heading[0]; $("#pageSubtitle").textContent=heading[1];
  $("#pageEyebrow").textContent="THE MIRROR / " + heading[2];
  $("#pageNote").textContent=heading[3];
  $$(".page").forEach(p => p.classList.add("hidden"));
  $("#page-" + name).classList.remove("hidden");
  $$("[data-page]").forEach(t => {const active=t.dataset.page===name;t.classList.toggle("active",active);if(active)t.setAttribute('aria-current','page');else t.removeAttribute('aria-current');});
  if (!fromRoute) {
    const target = "#/" + name;
    if (location.hash !== target) history.pushState(null, "", target);
  }
  if (!loaded[name] && getToken()) { loaded[name] = true; Promise.resolve(loaders[name]()).catch(e => { loaded[name]=false; toast(e.message); }); }
  if (name === "graph") requestAnimationFrame(() => resizeGraphCanvas());
}
$$("[data-page]").forEach(t =>
  t.addEventListener("click", () => {switchPage(t.dataset.page);$('#pageTitle').tabIndex=-1;$('#pageTitle').focus({preventScroll:true});}));

/* ================= ① 对话 ================= */
function showSlices(meta) {
  const root = $("#sliceInfo");
  if (!meta || typeof meta !== "object") { root.textContent = "正在读取个人档案、相关历史与三盘…"; return; }
  const names = {bazi:"八字", ziwei:"紫微", astro:"星盘"};
  root.innerHTML = Object.entries(meta.chart_status || {}).map(([k,v]) => `<span class="badge ${v === "ok" ? "badge-purple" : "badge-gray"} mr-1">${names[k] || k} · ${v === "ok" ? "已计算" : "数据不足"}</span>`).join("")
    + `<div class="text-xs text-gray-400 mt-2">已接入 ${meta.history_messages || 0} 条双端对话 · ${meta.records || 0} 条相关档案</div>`;
}
function todayDate() {return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
function chartDate() { return $("#analysisDate")?.value || todayDate(); }
function analysisFocus() { return $("#analysisFocus")?.value || "综合"; }
async function refreshLinkedCharts() {
  ziweiLoaded = false; astroLoaded = false;
  await Promise.all([loadChart(),loadZiwei(),loadAstro()]);
}
function askLinked(system,key,label) {
  const selection = {system,key:String(key),date:chartDate(),focus:analysisFocus()};
  closeDrawer(); switchPage("chat");
  sendChat(`请深入解读${label}，分析日期${selection.date}，重点${selection.focus}。请结合实际盘面解释三盘联动、支持与冲突、行动建议和可核对的观察点。`, selection);
}
function renderZiweiLinks(p) {
  const links=p.linked_palaces || [];
  const h=(ziweiData || {}).horoscope || {};
  const selected=new Set([p.index,...links.map(x=>x.index)]);
  return `<div class="glass p-4 mt-4"><div class="gold-text mb-2">三方四正 · 点击切换宫位</div>${links.map(x=>`<button class="badge badge-purple mr-2 mb-2" onclick="openPalaceDetail(${x.index})">${esc(x.relation)} · ${esc(x.name)} · ${esc((x.major || []).map(s=>s.name).join('、') || '空宫')}</button>`).join('')}
  ${['decadal','yearly','monthly','daily'].map(k=>{const v=h[k] || {};const changes=(v.mutagen_links || []).filter(x=>selected.has(x.palace_index));return `<div class="text-xs text-gray-300 mt-2">${esc(v.name || k)} ${esc(v.ganzhi || '')}：${esc(changes.map(x=>`${x.star}化${x.mutagen} → 本命${x.natal_palace} / ${x.scope_palace}`).join('；') || '本组宫位无四化落点')}</div>`;}).join('')}</div>`;
}
function renderAstroLinks(key) {
  const c=astroData || {}, name=key.startsWith('p:')?key.slice(2):key;
  const natal=(c.aspects || []).filter(x=>x.from===name || x.to===name);
  const transit=((c.transits || {}).aspects_to_natal || []).filter(x=>x.to===name);
  const list=(arr,moving)=>arr.length?arr.map(x=>`<div class="text-xs text-gray-300 py-1">${moving?'行运':''}${esc(x.from)} ${esc(x.aspect)} ${moving?'本命':''}${esc(x.to)} · 容许度 ${x.orb}°</div>`).join(''):'<div class="text-xs text-gray-500">当前计算范围内无相位记录</div>';
  return `<div class="glass p-4 mt-4"><div class="gold-text mb-2">本命相位</div>${list(natal,false)}<div class="gold-text mt-3 mb-2">${esc((c.transits || {}).date || chartDate())} 行运联动</div>${list(transit,true)}<div class="text-xs text-gray-500 mt-3">行运采用当日12时快照，不能据此推断事件的精确时刻。</div></div>`;
}

function addUserMsg(text, images) {
  const d = document.createElement("div");
  d.className = "flex justify-end";
  const imgsHtml = (images && images.length)
    ? `<div class="flex gap-2 flex-wrap justify-end mb-2">${images.map(u =>
        `<img src="${u}" class="w-20 h-20 object-cover rounded-lg border border-white/10 cursor-pointer chat-img" alt="附图">`).join("")}</div>`
    : "";
  d.innerHTML = `<div class="msg-user px-4 py-3 max-w-[85%] msg-body">${imgsHtml}${esc(text).replace(/\n/g, "<br>")}</div>`;
  $("#chatFlow").appendChild(d);
  scrollChat();
}
function addAiMsg() {
  const d = document.createElement("div");
  d.className = "flex justify-start";
  d.innerHTML = `<div class="msg-ai px-4 py-3 max-w-[92%] w-fit min-w-[120px]">
      <div class="msg-body type-caret"><span class="text-gray-500 text-sm">明镜推演中…</span></div>
    </div>`;
  $("#chatFlow").appendChild(d);
  scrollChat();
  return d.querySelector(".msg-body");
}
function scrollChat(force=true) { const f = $("#chatFlow"); if(force || f.scrollHeight-f.scrollTop-f.clientHeight<140) f.scrollTop = f.scrollHeight; }

/* ---- 对话历史回显：/api/history 返回网页+飞书合并时间线（按时间正序），最多渲染最近 30 条 ---- */
let historyLoaded = false;
function dividerHtml(text) {
  return `<div class="flex items-center gap-3 text-[11px] text-gray-600 select-none">
    <div class="flex-1 border-t border-white/10"></div>
    <div>${esc(text)}</div>
    <div class="flex-1 border-t border-white/10"></div>
  </div>`;
}
function fmtHistTime(at) {
  const value=String(at || ''),m=/^\d{4}-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(value);
  if(!m)return '';
  // Legacy timestamps without an offset retain their recorded local time.
  if(!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value))return `${m[1]}-${m[2]} ${m[3]}:${m[4]}`;
  const date=new Date(value);if(!Number.isFinite(date.getTime()))return '';
  const parts=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(date).map(p=>[p.type,p.value]));
  return `${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}
function srcBadgeHtml(m) {  // 来源徽章：飞书=紫微紫，网页=鎏金
  if (m.source === "feishu") return `<span class="src-badge src-feishu">飞书</span>`;
  if (m.source === "web") return `<span class="src-badge src-web">网页</span>`;
  return "";
}
function histMsgHtml(m) {
  const time = fmtHistTime(m.at);
  const timeHtml = time ? `<div class="text-right text-[10px] text-gray-500 mt-1.5">${esc(time)}</div>` : "";
  const badge = srcBadgeHtml(m);
  if (m.role === "user") {
    let text = String(m.content || "");
    let imgNote = "";
    const im = / \[附图\d+张\]\s*$/.exec(text);  // 历史不含图片本体，标记降级为小字提示
    if (im) { text = text.slice(0, im.index); imgNote = `<div class="text-right text-[10px] text-gray-400 mt-1">[附图]</div>`; }
    return `<div class="flex justify-end">
      <div class="msg-user relative px-4 py-3 max-w-[85%] msg-body">${badge}${esc(text).replace(/\n/g, "<br>")}${imgNote}${timeHtml}</div>
    </div>`;
  }
  return `<div class="flex justify-start">
    <div class="msg-ai relative px-4 py-3 max-w-[92%] w-fit min-w-[120px]">${badge}<div class="msg-body" ${m.meta?.meta?.core_run?.run_id || m.context_meta?.meta?.core_run?.run_id?`data-core-run="${esc((m.meta || m.context_meta).meta.core_run.run_id)}"`:''}>${answerHtml(m.meta || m.context_meta, m.content)}</div>${timeHtml}</div>
  </div>`;
}
let currentSession=localStorage.getItem("mjt_session") || "shared", historyBefore="", historyRows=[];
function storedJson(key, fallback, storage=sessionStorage) {try {return JSON.parse(storage.getItem(key)) ?? fallback;} catch {return fallback;}}
function chatContext() {return storedJson('context:'+currentSession,{});}
let chatScopeCases=[];
function contextCaseIds(context=chatContext()) {return [...new Set(Array.isArray(context.case_ids)?context.case_ids:context.case_id?[context.case_id]:[])].filter(id=>typeof id==='string' && id);}
function setChatContext(context) {context={...(context || {})};context.case_ids=context.draw_id?[context.draw_case_id || context.case_id].filter(Boolean):contextCaseIds(context);context.case_id=context.case_ids[0] || null;if(context.draw_id)context.draw_case_id=context.case_id;sessionStorage.setItem('context:'+currentSession,JSON.stringify(context));renderChatContext();renderChatScope();}
async function loadChatScope() {
  const root=$('#chatCaseScopeList');root.innerHTML='<p class="muted">正在读取有效事项…</p>';
  try{const rows=await apiJson('/api/cases?subject_id=self');chatScopeCases=(Array.isArray(rows)?rows:[]).filter(row=>(row.subject_id || row.subject || 'self')==='self' && !['deleted','stopped','revoked','cancelled'].includes(row.status));renderChatScope();}
  catch(e){root.innerHTML=`<p class="err-banner" role="alert">事项范围暂时无法读取：${esc(e.message)}</p><button class="quiet-button" data-reload-chat-scope>重新读取</button>`;root.querySelector('button').onclick=loadChatScope;}
}
function renderChatScope() {
  const context=chatContext(),ids=contextCaseIds(context),root=$('#chatCaseScopeList');
  $('#chatCaseScopeCount').textContent=context.draw_id?'固定牌阵对应事项':ids.length?'已选 '+ids.length+' 件':'未关联事项';
  root.innerHTML=(context.draw_id?'<p class="muted">本轮牌阵的事项已固定。解除牌阵后，可重新选择范围。</p><button class="quiet-button" data-unlink-chat-draw>解除牌阵关联</button>':'')+(chatScopeCases.length?chatScopeCases.map(entry=>`<label class="chat-case-choice"><input type="checkbox" data-chat-case="${esc(entry.id)}" ${ids.includes(entry.id)?'checked':''} ${context.draw_id?'disabled':''}><span>${esc(entry.title || '未命名事项')}</span></label>`).join(''):'<p class="muted">暂无可选事项。可以先到“我的事项”记录。</p>');
  root.querySelector('[data-unlink-chat-draw]')?.addEventListener('click',()=>{const {draw_id,draw_case_id,...other}=context;setChatContext(other);});
  root.querySelectorAll('[data-chat-case]').forEach(input=>input.onchange=()=>{if(sending){input.checked=!input.checked;toast('本轮正在处理，完成后可调整下一轮范围');return;}const chosen=[...root.querySelectorAll('[data-chat-case]:checked')].map(input=>input.dataset.chatCase);if(chosen.length>8){input.checked=false;toast('每轮最多选择 8 个事项');return;}const focused=input.dataset.chatCase;setChatContext({case_ids:chosen,title:chatScopeCases.filter(entry=>chosen.includes(entry.id)).map(entry=>entry.title).join('、')});[...root.querySelectorAll('[data-chat-case]')].find(input=>input.dataset.chatCase===focused)?.focus();});
}
$('#chatCaseScope').addEventListener('toggle',()=>{if($('#chatCaseScope').open)loadChatScope();});
function renderChatContext() {
  const c=chatContext(), root=$('#chatCaseBar');
  root.classList.toggle('hidden',!contextCaseIds(c).length && !c.draw_id);
  root.innerHTML=`<span>${esc(c.title || '继续当前事项')}${c.draw_id?' · 已关联固定牌阵':''}</span><div>${c.draw_id?'<button data-open-linked-draw>查看牌阵</button>':''}<button data-clear-linked-case aria-label="解除本轮事项关联">聊另一件事</button></div>`;
  root.querySelector('[data-open-linked-draw]')?.addEventListener('click',()=>openTarotDraw(c.draw_id));
  root.querySelector('[data-clear-linked-case]')?.addEventListener('click',()=>setChatContext({}));
}
const blobImages=new Map();
async function hydrateImages(root) {
  for(const img of root.querySelectorAll("img[data-image]")) {
    try {
      const id=img.dataset.image;
      if(!blobImages.has(id)) { const r=await api("/api/images/"+id); if(!r.ok) throw Error(); blobImages.set(id,URL.createObjectURL(await r.blob())); }
      img.src=blobImages.get(id);
    } catch {img.replaceWith(document.createTextNode("图片暂时无法读取"));}
  }
}
function realityContextHtml(result) {
  const rows=Array.isArray(result?.reality_context)?result.reality_context:[];
  const kinds={known:'已知现实',preference:'你的偏好',assumption:'仍是假设',missing:'还缺的信息'};
  const groups=Object.entries(kinds).map(([kind,label])=>{const entries=rows.filter(row=>row?.kind===kind && typeof row.statement==='string' && row.statement.trim());return entries.length?`<section class="reality-group reality-${kind}"><h4>${label}</h4>${entries.map(row=>`<p>${esc(row.statement)}</p>`).join('')}</section>`:'';}).join('');
  return groups?`<section class="answer-reality"><h3>这次依据哪些现实信息</h3><div class="reality-groups">${groups}</div></section>`:'';
}
function tarotAnswerDetails(result) {
  const cards=Array.isArray(result?.card_interpretations)?result.card_interpretations:[],relations=typeof result?.tarot_synthesis==='string'?[result.tarot_synthesis]:Array.isArray(result?.tarot_synthesis)?result.tarot_synthesis:[];
  const cardSections=cards.map(c=>{const name=c.card?.name || c.name || tarotCard(c.card_id).name || c.card_id || '已保存的牌';return `<section class="answer-detail-section tarot-card-interpretation"><h3>第 ${esc(c.position)} 张 · ${esc(name)} ${tarotOrientation(c.orientation)}</h3><p class="detail-note">象征主题：${esc(c.theme)}</p><p>${esc(c.interpretation)}</p>${c.question?`<p>可以想一想：${esc(c.question)}</p>`:''}</section>`;}).join('');
  const relationSection=relations.length?`<section class="answer-detail-section tarot-relations"><h3>这些角度之间</h3>${relations.map(row=>`<p>${esc(typeof row==='string'?row:row?.interpretation || row?.theme || '')}</p>`).join('')}</section>`:'';
  return cardSections+relationSection;
}
function evidenceHtml(result) {
  if(!result) return "";
  const list=value=>Array.isArray(value)?value:[];
  const evidence=[...list(result.evidence)], memories=list(result.memory_receipts).filter(m=>m?.write_status==='saved'), synthesis=list(result.synthesis), caveats=list(result.caveats);
  for(const row of list(result.reality_context))if(row?.ref && !evidence.some(e=>e.ref===row.ref))evidence.push({ref:row.ref,claim:row.statement,source:'user_context'});
  const appendix=typeof result.professional_appendix==='string'?result.professional_appendix.trim():'';
  const engineNames={bazi:'八字',ziwei:'紫微斗数',astro:'西方星盘',tarot:'塔罗'};
  const relationshipNames={aligned:'侧重点相近',mixed:'部分相近',divergent:'侧重点不同',insufficient:'资料不足'};
  const contributionNames={used:'本次参考',not_relevant:'与此问题关联较弱',unavailable:'暂无可用资料',notused:'本次未使用',uncertain:'仍不确定'};
  const raw=value=>value!==null && typeof value==='object'?'详见来源说明':esc(value);
  const sourceName=e=>{
    const engine=String(e.ref || '').split(':')[1];
    if(String(e.ref || '').startsWith('chart:') && engineNames[engine])return engineNames[engine]+' · 计算资料';
    if(String(e.ref || '').startsWith('draw:'))return '本次固定抽牌';
    if(String(e.ref || '').startsWith('tarot:'))return '本次牌意参考';
    return ({memory:'你的记录',user:'你的原话',user_message:'你的原话',user_context:'现实背景来源',current_user_statement_not_saved:'本轮原话（未保存为长期记忆）',web:'网页对话',feishu:'飞书对话',report:'历史报告',reports:'历史报告',archive:'个人档案',image:'本次图片'})[e.source] || '参考资料';
  };
  const comparison=synthesis.length?`<section class="answer-detail-section"><h3>${synthesis.some(s=>list(s.contributions).some(c=>c.engine==='tarot'))?'不同象征视角如何参考':'三盘如何一起参考'}</h3><p class="detail-note">这里比较的是不同传统的解释角度；相似的象征不代表现实事件更可能发生。</p>${synthesis.map(s=>`<article class="synthesis-theme"><div class="synthesis-heading"><h4>${esc(s.theme)}</h4><span>${esc(relationshipNames[s.relationship] || '对照说明')}</span></div><p>${esc(s.interpretation)}</p><div class="synthesis-contributions">${list(s.contributions).map(c=>`<div class="synthesis-contribution"><div><strong>${esc(engineNames[c.engine] || '盘面')}</strong><small>${esc(contributionNames[c.status] || '参考说明')}</small></div><p>${esc(c.reason)}</p>${list(c.evidence).length?`<details class="source-record"><summary>核对盘面字段</summary>${list(c.evidence).map(e=>`<pre>${esc(e.ref)}${e.path?'\n'+esc(e.path):''}${e.value!==undefined?'\n'+raw(e.value):''}</pre>`).join('')}</details>`:''}</div>`).join('')}</div></article>`).join('')}</section>`:'';
  const sources=evidence.length?`<section class="answer-detail-section"><h3>参考了哪些资料</h3>${evidence.map(e=>`<div class="source-item"><b>${esc(sourceName(e))}</b><p>${esc(e.claim)}</p><details class="source-record"><summary>查看原始资料</summary>${e.ref?`<p class="detail-note">来源标记：${esc(e.ref)}</p>`:''}${e.path || e.value!==undefined?`<pre>${e.path?esc(e.path):''}${e.value!==undefined?'\n'+raw(e.value):''}</pre>`:''}${e.data!==undefined?readableSource(e.data):'<p>本轮已核对来源；暂无更多可展示节选。</p>'}</details></div>`).join('')}</section>`:'';
  const methodLimits=calculationLimitsHtml(result);
  const boundaries=caveats.length || methodLimits?`<section class="answer-detail-section answer-method-limits"><h3>资料缺口与解释边界</h3>${caveats.map(x=>`<p>${esc(x)}</p>`).join('')}${methodLimits}</section>`:'';
  const coverage=list(result.coverage).length?`<section class="answer-detail-section answer-coverage"><h3>本次参考范围</h3>${list(result.coverage).map(c=>`<p><strong>${esc(engineNames[c.engine] || '参考视角')}</strong> · ${esc(contributionNames[c.status] || '参考说明')}<br>${esc(c.reason)}</p>`).join('')}</section>`:'';
  const tarotDetails=tarotAnswerDetails(result),professional=appendix?`<section class="answer-detail-section professional-appendix"><h3>专业解读</h3>${md(appendix)}</section>`:'';
  const saved=memories.length?`<button class="memory-notice" onclick="switchPage('memory')">本轮已保存 ${memories.length} 条长期信息 · 查看原话与更正 ↗</button>`:'';
  return saved+((comparison || sources || boundaries || professional || tarotDetails || coverage)?`<details class="answer-sources"><summary><span>${tarotDetails?'牌面解释、专业依据与来源':synthesis.length?'专业依据与三盘对照':'专业依据与来源'}</span><small>按需展开</small></summary><div class="answer-details-body">${tarotDetails}${comparison}${coverage}${sources}${boundaries}${professional}</div></details>`:'');
}
function calculationFallbackHtml(rows) {
  if(!Array.isArray(rows))return '';
  return rows.filter(row=>row && typeof row.requested==='string' && typeof row.actual==='string').map(row=>`<p class="calculation-fallback">实际回退：${esc(row.requested)} → ${esc(row.actual)}${row.body?' · '+esc(row.body):''}${row.layer?' · '+esc(({natal:'本命',transit_snapshot:'目标日快照'})[row.layer] || row.layer):''}${Number.isInteger(row.returned_flags)?' · 引擎标志 '+esc(row.returned_flags):''}</p>`).join('');
}
function calculationLimitsHtml(result) {
  const systems={bazi:'八字',ziwei:'紫微斗数',astro:'西方星盘',tarot:'塔罗'},labels={RULE_GAP:'尚无已实现解释规则',unsupported:'本次不支持',UNSUPPORTED:'本次不支持',UNSUPPORTED_INFERENCE:'超出已允许解释范围',MISSING_INPUT:'所需计算资料缺失',CALCULATION_ERROR:'计算未完成',REFERENCE_ERROR:'字段引用未通过核验',SCOPE_MISMATCH:'解释范围不匹配',AUTH_SCOPE_ERROR:'授权范围不匹配',STALE_INPUT:'依据已更新',DRAW_MISMATCH:'固定牌面不匹配'};
  const list=value=>Array.isArray(value)?value:[];
  const gaps=list(result?.coverage_gaps).filter(row=>row && typeof row==='object').map(row=>`<div class="calculation-gap"><p><strong>${esc(systems[row.system] || '解释范围')}</strong> · ${esc(row.status || 'RULE_GAP')} · ${esc(labels[row.status] || '资料需核对')}${row.rule_id?' · '+esc(row.rule_id):''}</p>${row.reason?`<p>${esc(row.reason)}</p>`:''}${list(row.issues).filter(issue=>issue && typeof issue==='object').map(issue=>`<p>${esc(issue.code || '')}${issue.detail?'：'+esc(issue.detail):''}</p>`).join('')}</div>`).join('');
  const errors=list(result?.calculation_errors).filter(row=>row && typeof row==='object').map(row=>`<p class="calculation-error"><strong>${esc(systems[row.system] || '计算范围')}</strong> · ${esc(row.code || 'CALCULATION_ERROR')} · ${esc(row.reason || labels[row.code] || '计算未完成')}</p>`).join('');
  return gaps+errors+calculationFallbackHtml(result?.calculation_fallbacks);
}
function answerHtml(result, fallback='') {
  return `<div class="answer-reading">${md(result?.answer || fallback || result?.plain_summary || '')}${realityContextHtml(result)}</div>${evidenceHtml(result)}`;
}
function historyItemHtml(m) {
  let html=histMsgHtml(m);
  if(m.role==='user') {
    const images=(m.image_ids || []).map(id=>`<img data-image="${esc(id)}" alt="历史附图" class="chat-img history-image">`).join('');
    let state='';
    if(['failed','stale','interrupted'].includes(m.status)) state=`<button class="quiet-button retry-history" data-turn="${esc(m.turn_id)}">未完成 · 继续本轮</button>`;
    if(m.status==='cancelled')state='<span class="muted">本轮已停止</span>';
    if(m.status==='running')state='<span class="muted">仍在处理，稍后刷新可回看</span>';
    html+=`<div class="history-attachments">${images}${state}</div>`;
  }
  return html;
}
function bindHistory(root) {
  hydrateImages(root);
  root.querySelectorAll('[data-core-run]').forEach(body=>{const message=historyRows.find(row=>row.role==='assistant' && (row.meta || row.context_meta)?.meta?.core_run?.run_id===body.dataset.coreRun);if(message)bindClarification(body,message.meta || message.context_meta);});
  root.querySelectorAll('.retry-history').forEach(b=>b.onclick=()=>{
    const m=historyRows.find(x=>x.turn_id===b.dataset.turn && x.role==='user');
    if(m)sendChat(m.content,null,m.run_id || m.turn_id);
  });
}
function refreshSynastryConsents() {
  if(typeof renderSynastryConsents!=='function')return;
  const flow=$('#chatFlow');if(!flow)return;
  let root=flow.querySelector('[data-synastry-confirmations]');
  if(!root){root=document.createElement('div');root.dataset.synastryConfirmations='';flow.append(root);}
  const session=currentSession,token=getToken();
  renderSynastryConsents(root,{apiJson,conversationId:session,isCurrent:()=>session===currentSession && token===getToken()});
}
async function loadHistory(older=false) {
  const session=currentSession;
  const flow=$("#chatFlow");
  try {
    const list=await apiJson(`/api/history?session=${encodeURIComponent(session)}&limit=60${older && historyBefore?'&before='+encodeURIComponent(historyBefore):''}`);
    if(session!==currentSession)return;
    if(!older) {flow.innerHTML='';historyRows=[];}
    if(list.length)historyBefore=list[0].cursor || list[0].at;
    historyRows=older?[...list,...historyRows]:list;
    const wrap=document.createElement('div');wrap.className='space-y-4';wrap.innerHTML=list.map(historyItemHtml).join('');
    const previousHeight=flow.scrollHeight;
    if(older)flow.prepend(wrap);else flow.append(wrap);
    bindHistory(wrap);
    refreshSynastryConsents();
    $('#olderHistoryBtn').disabled=list.length<60;
    if(!historyRows.length)flow.innerHTML=`<div class="chat-welcome"><span>明镜，映照日常。</span><h2>今天，从哪件事聊起？</h2><p>可以说说近况，上传一张图片，或从命盘中选一个细节展开。你的经历和想法，始终是解读的起点。</p></div>`;
    if(older)flow.scrollTop=flow.scrollHeight-previousHeight;else scrollChat();
    historyLoaded=true;
  } catch(e) {if(!older)flow.innerHTML=errState('历史暂时无法读取：'+e.message,'loadHistory');}
}
async function loadSessions() {
  const list=await apiJson('/api/sessions');
  if(!list.some(s=>s.id===currentSession))currentSession='shared';
  $('#conversationTitle').textContent=list.find(s=>s.id===currentSession)?.title || '与明镜对话';
  $('#sessionSelect').innerHTML=list.map(s=>`<option value="${esc(s.id)}" ${s.id===currentSession?'selected':''}>${esc(s.title)}</option>`).join('');
  $('#sessionList').innerHTML=list.slice(0,30).map(s=>`<button data-session="${esc(s.id)}" class="session-item ${s.id===currentSession?'active':''}" title="${esc(s.title)}">${esc(s.title)}</button>`).join('');
  $('#sessionList').querySelectorAll('button').forEach(b=>b.onclick=()=>activateSession(b.dataset.session));
}
async function activateSession(ident) {
    if(sending){toast('请等待本轮结束，或先停止回答');return;}
    sessionStorage.setItem('draft:'+currentSession,$('#chatInput').value);
    currentSession=ident;localStorage.setItem('mjt_session',currentSession);
    renderChatContext();
    $('#chatInput').value=sessionStorage.getItem('draft:'+currentSession)||'';
    switchPage('chat');await loadSessions();await loadHistory();
}
async function newConversation() {
  if(sending){toast('请等待本轮结束，或先停止回答');return;}
  try { const s=await writeJson('/api/sessions',{});
    currentSession=s.id;localStorage.setItem('mjt_session',s.id);renderChatContext();$('#chatInput').value='';switchPage('chat');await loadSessions();await loadHistory();
  } catch(e){toast(e.message);}
}
/* 待发附图：选图 → 缩略图条 → 随消息一起发送 */
const MAX_IMGS = 4, MAX_IMG_BYTES = 5 * 1024 * 1024;
let pendingImgs = [];  // data URL 数组

function renderImgStrip() {
  const strip = $("#imgStrip");
  if (!pendingImgs.length) { strip.classList.add("hidden"); strip.innerHTML = ""; return; }
  strip.classList.remove("hidden");
  strip.innerHTML = pendingImgs.map((u, i) => `
    <div class="relative shrink-0">
      <img src="${u}" class="w-14 h-14 object-cover rounded-lg border border-white/15" alt="附图${i + 1}">
      <button data-i="${i}" class="img-del absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full text-xs leading-none"
        style="background:#1A1E2E;border:1px solid rgba(217,106,91,.6);color:#F0A79D;">×</button>
    </div>`).join("");
  strip.querySelectorAll(".img-del").forEach(b =>
    b.addEventListener("click", () => { pendingImgs.splice(Number(b.dataset.i), 1); renderImgStrip(); }));
}

$("#imgBtn").addEventListener("click", () => $("#imgInput").click());
$('#imgInput').addEventListener('change',async e=>{
 const files=Array.from(e.target.files || []);e.target.value='';
 for(const f of files){
   if(pendingImgs.length>=MAX_IMGS){toast('最多附4张图');break;}
   if(!['image/jpeg','image/png','image/webp'].includes(f.type)){toast('支持 JPG、PNG、WebP 图片');continue;}
   if(f.size>MAX_IMG_BYTES){toast('图片超过5MB，请压缩后再传');continue;}
   const url=await new Promise((resolve,reject)=>{const rd=new FileReader();rd.onload=()=>resolve(rd.result);rd.onerror=reject;rd.readAsDataURL(f);}).catch(()=>null);
   if(url && pendingImgs.length<MAX_IMGS){pendingImgs.push(url);renderImgStrip();}
 }
});

function closeImageViewer(){ $('#imgViewer').classList.add('hidden');restoreFocus('image'); }
$("#imgViewer").addEventListener("click",closeImageViewer);
$("#chatFlow").addEventListener("click", e => {
  if (e.target.classList.contains("chat-img")) {
    rememberFocus('image');
    $("#imgViewerImg").src = e.target.src;
    $("#imgViewer").classList.remove("hidden");
  }
});

let sending = false, activeTurn=null;
const chatRequests=new Map();
function progress(text) {$('#chatProgress').textContent=text;$('#chatProgress').classList.remove('hidden');}
function renderAnswer(body,result) { body.classList.remove('type-caret');body.innerHTML=answerHtml(result);bindClarification(body,result);refreshSynastryConsents();const m=result?.meta || {},caseId=m.case_id || m.case_ids?.[0];if(Array.isArray(m.case_ids) || caseId)setChatContext({case_ids:m.case_ids || [caseId],case_id:caseId,title:m.case_title || chatScopeCases.filter(entry=>(m.case_ids || [caseId]).includes(entry.id)).map(entry=>entry.title).join('、'),...(m.draw_id?{draw_id:m.draw_id,draw_case_id:caseId}:{})});scrollChat(false); }
function bindClarification(body,result) {
  const interrupt=result?.meta?.interrupt,runId=result?.meta?.core_run?.run_id;
  if(!interrupt?.id || !interrupt.state_version || !runId)return;
  const form=document.createElement('form');form.className='clarification-form';form.innerHTML=`${Array.isArray(interrupt.questions) && interrupt.questions.length?`<ul>${interrupt.questions.map(question=>`<li>${esc(question)}</li>`).join('')}</ul>`:''}<label>补充这次缺少的信息<textarea rows="2" maxlength="16000" required aria-label="补充本轮澄清信息"></textarea></label><p class="muted">补充后会重新读取最新有效资料，沿用这轮选中的人物、事项与固定牌阵。</p><button type="submit" class="btn-gold">补充并继续</button>`;
  form.onsubmit=async event=>{event.preventDefault();const message=form.querySelector('textarea').value.trim();if(!message || sending)return;await sendChat(message,null,null,{runId,interruptId:interrupt.id,stateVersion:interrupt.state_version,caseIds:result.meta.case_ids || [],drawId:result.meta.draw_id});};body.append(form);
}
async function recoverTurn(body,id) {
  progress('连接已断开，正在重新查找本轮结果…');
  for(let i=0;i<90;i++) {
    const turn=await apiJson('/api/chat/'+encodeURIComponent(id));
    if(turn.status==='complete'){renderAnswer(body,turn.meta?.answer?turn.meta:{answer:turn.answer});return;}
    if(turn.status!=='running')throw Error(turn.meta?.error || (turn.status==='cancelled'?'已停止本轮回答':'本轮中断，可重试'));
    await new Promise(resolve=>setTimeout(resolve,5000));
  }
  throw Error('本轮仍在后台处理中，请稍后从历史回看');
}
async function sendChat(msg, selection = null, retryOf = null, resumeSpec = null) {
  msg=String(msg || '').trim();if(!msg || sending)return;
  const pending=storedJson('chat-retry:'+currentSession,null);
  if(!retryOf && pending?.message===msg && JSON.stringify(pending.selection || null)===JSON.stringify(selection)){retryOf=pending.run_id;resumeSpec ||=pending.resumeSpec;}
  if(!getToken()){openTokenModal(false);return;}
  sending=true;$('#sendBtn').disabled=true;$('#stopBtn').classList.remove('hidden');
  $('#chatInput').value='';sessionStorage.removeItem('draft:'+currentSession);
  const imgs=resumeSpec?[]:pendingImgs.slice();if(!resumeSpec)pendingImgs=[];renderImgStrip();addUserMsg(msg,imgs);
  if(selection){$('#selectionChip').textContent=`${selection.date} · ${selection.system} · ${selection.focus}`;$('#selectionChip').classList.remove('hidden');}
  else $('#selectionChip').classList.add('hidden');
  const body=addAiMsg();let gotResult=false, serverError=null;
  const context=chatContext(), previous=retryOf?(chatRequests.get(retryOf) || storedJson('chat-pending:'+retryOf,null)):null;
  const messageId=resumeSpec?tarotOperationKey('resume:'+resumeSpec.runId+':'+resumeSpec.interruptId,{message:msg,state_version:resumeSpec.stateVersion}):null;
  const id=previous?.request_id || retryOf || (resumeSpec?'resume:'+resumeSpec.runId+':'+messageId:crypto.randomUUID());
  const caseIds=resumeSpec?resumeSpec.caseIds:context.draw_id?[context.draw_case_id || context.case_id].filter(Boolean):contextCaseIds(context);
  const drawId=resumeSpec?resumeSpec.drawId:context.draw_id;
  const payload=previous || {message:msg,selection:selection || {},images:imgs,session_id:currentSession,request_id:id,case_ids:caseIds,...(caseIds[0]?{case_id:caseIds[0]}:{}),...(drawId?{draw_id:drawId}:{}),...(resumeSpec?{resume:{...resumeSpec,messageId}}:{})};
  chatRequests.set(id,payload);
  if(JSON.stringify(payload).length<200000)try{sessionStorage.setItem('chat-pending:'+id,JSON.stringify(payload));}catch{}
  activeTurn=retryOf || id;progress(retryOf?'正在恢复原来这一轮…':'正在保存问题与附图…');
  try {
    let r;
    if(retryOf){
      let run;
      try{run=await apiJson('/api/runs/'+encodeURIComponent(retryOf));}catch(e){if(e.status!==404)throw e;}
      if(run?.status==='succeeded'){gotResult=true;renderAnswer(body,run.result);return;}
      if(run && ['running','queued'].includes(run.status)){await recoverTurn(body,run.id);gotResult=true;return;}
      if(run){r=await api('/api/runs/'+encodeURIComponent(run.id)+'/retry',{method:'POST',body:JSON.stringify({request_id:'retry:'+run.operation_id})});}
    }
    r ||= payload.resume?await api('/api/runs/'+encodeURIComponent(payload.resume.runId)+'/resume',{method:'POST',body:JSON.stringify({message:payload.message,message_id:payload.resume.messageId,interrupt_id:payload.resume.interruptId,state_version:payload.resume.stateVersion})}):await api('/api/chat',{method:'POST',body:JSON.stringify(payload)});
    if(!r.ok){let detail=await r.json().catch(()=>({}));throw Error(detail.detail || `请求失败 (${r.status})`);}
    const reader=r.body.getReader(),dec=new TextDecoder();let buffer='';
    try {
      while(true){
        const {done,value}=await reader.read();if(done)break;buffer+=dec.decode(value,{stream:true});let pos;
        while((pos=buffer.indexOf('\n'))>=0){
          const line=buffer.slice(0,pos).trim();buffer=buffer.slice(pos+1);if(!line.startsWith('data:'))continue;
          const data=line.slice(5).trim();if(data==='[DONE]')continue;
          const event=JSON.parse(data);
          if(event.type==='started' && event.run_id){activeTurn=event.run_id;chatRequests.set(event.run_id,payload);}
          if(event.type==='context')showSlices(event.meta);
          if(event.type==='status' || event.type==='tool')progress(event.text);
          if(event.type==='result'){gotResult=true;renderAnswer(body,event.result);loaded.memory=false;loaded.cases=false;}
          if(event.type==='error')serverError=event.message;
        }
      }
    } catch(e){if(!gotResult && !serverError)progress('连接波动，正在恢复本轮…');}
    if(serverError)throw Error(serverError);
    if(!gotResult){await recoverTurn(body,activeTurn || id);gotResult=true;}
  } catch(e) {
    const restoreId=activeTurn || retryOf || id;
    sessionStorage.setItem('chat-retry:'+currentSession,JSON.stringify({run_id:restoreId,message:msg,selection,resumeSpec}));
    body.classList.remove('type-caret');body.innerHTML=`<div class="err-banner" role="alert">${esc(e.message || e)}</div><button class="quiet-button retry-current">继续原来这一轮</button><p class="muted">问题和附图已保留；继续本轮会沿用原来的记录。</p><details class="new-round-options"><summary>需要重新开始？</summary><p class="muted">开始新一轮会建立新的问题记录和调用预算。</p><button class="quiet-button new-round-current">明确开始新一轮</button></details>`;
    body.querySelector('.retry-current').onclick=()=>{if(!sending)sendChat(msg,selection,restoreId,resumeSpec);};
    body.querySelector('.new-round-current').onclick=()=>{if(!sending){sessionStorage.removeItem('chat-retry:'+currentSession);pendingImgs=imgs.slice();sendChat(msg,selection);}};
    if(!$('#chatInput').value){$('#chatInput').value=msg;sessionStorage.setItem('draft:'+currentSession,msg);}
    if(!pendingImgs.length){pendingImgs=imgs.slice();renderImgStrip();}
  } finally {
    if(gotResult){sessionStorage.removeItem('chat-pending:'+id);sessionStorage.removeItem('chat-retry:'+currentSession);chatRequests.delete(id);chatRequests.delete(activeTurn);}
    sending=false;activeTurn=null;$('#sendBtn').disabled=false;$('#stopBtn').classList.add('hidden');$('#chatProgress').classList.add('hidden');
    loadSessions().catch(()=>{});$('#chatInput').focus();
  }
}
$('#stopBtn').onclick=async()=>{if(activeTurn)try{await writeJson('/api/runs/'+encodeURIComponent(activeTurn)+'/cancel',{});progress('正在停止…');}catch(e){toast(e.message);}};
$('#sendBtn').onclick=()=>sendChat($('#chatInput').value);
$('#chatInput').addEventListener('keydown',e=>{if(e.key==='Enter' && !e.shiftKey && !e.isComposing){e.preventDefault();sendChat($('#chatInput').value);}});
$('#chatInput').addEventListener('input',()=>{sessionStorage.setItem('draft:'+currentSession,$('#chatInput').value);$('#chatInput').style.height='auto';$('#chatInput').style.height=Math.min(160,$('#chatInput').scrollHeight)+'px';});
$$('.chip').forEach(c=>c.onclick=async()=>{
  if(c.dataset.q!=='导出档案')return sendChat(c.dataset.q);
  try{downloadText('明镜台-个人档案.json',JSON.stringify(await apiJson('/api/archive'),null,2));}catch(e){toast(e.message);}
});
$('#olderHistoryBtn').onclick=()=>loadHistory(true);
$('#sessionSelect').onchange=()=>activateSession($('#sessionSelect').value);
$('#newSessionBtn').onclick=newConversation;$('#newChatMobileBtn').onclick=newConversation;

/* 右栏：档案速览 */
function renderMemorySettings(snapshot) {
  const root=$('#memorySettings');if(!snapshot){root.innerHTML='';return;}
  root.innerHTML=`<label class="memory-settings"><input id="autoSavePreference" type="checkbox" ${snapshot.settings?.auto_save_low_sensitivity!==false?'checked':''}> 自动保存低敏感的偏好与约束</label><p class="muted">出生资料、第三人信息等仍需明确授权；每次保存以回答下方的实际回执为准。</p>`;
  $('#autoSavePreference').onchange=async event=>{const input=event.target;input.disabled=true;try{await writeJson('/api/state/settings',{settings:{auto_save_low_sensitivity:input.checked},expected_revision:snapshot.revision},'PATCH');toast('记忆设置已更新');await loadMemories();}catch(e){input.checked=!input.checked;toast('设置尚未保存：'+e.message);}finally{input.disabled=false;}};
}
async function openProfile() {
  $('#profilePanel').open=true;await loadProfile();$('#profileRoot input')?.focus();
}
async function loadProfile() {
  const root=$('#profileRoot');root.innerHTML='<p class="muted">正在读取你确认过的出生资料…</p>';
  root.dataset.loading='true';
  try{
    const snapshot=await apiJson('/api/subjects/self/profile'),candidate=snapshot.legacy_candidate || {},flat=snapshot.effective || {},birth=candidate.birth || {},location=birth.location || {};
    const read=(field,fallback='')=>flat[field] ?? fallback;
    const dateTime=String(read('birth.solar_datetime',birth.solar_datetime || '')),precision=read('birth.precision',birth.time_unknown?'unknown':birth.precision || 'exact');
    root.innerHTML=`<form id="profileForm"><p class="muted">${snapshot.requires_explicit_confirmation?'以下资料来自历史档案，尚未作为已确认事实使用。请逐项核对，再明确授权保存。':'这些资料将作为你确认的个人事实使用。修改后需重新核对并授权。'}</p><div class="profile-fields">
      <label>排盘所用性别<select id="profileGender" required><option value="">请选择</option><option>男</option><option>女</option></select></label>
      <label>阳历出生日期<input id="profileDate" type="date" required value="${esc(dateTime.slice(0,10))}"></label>
      <label>出生时刻精度<select id="profilePrecision"><option value="exact">准确时刻</option><option value="approximate">大致时刻</option><option value="unknown">时刻未知</option></select></label>
      <label>当地出生时间<input id="profileTime" type="time" value="${esc(dateTime.slice(11,16))}"></label>
      <label id="profileUncertaintyLabel">前后误差（分钟）<input id="profileUncertainty" type="number" min="1" max="1440" step="1" value="${esc(read('birth.time_uncertainty_minutes',birth.time_uncertainty_minutes || ''))}"></label>
      <label>出生地名称<input id="profileCity" maxlength="120" required value="${esc(read('birth.location.city',location.city || location.name || ''))}"></label>
      <label>经度<input id="profileLng" type="number" min="-180" max="180" step="any" required value="${esc(read('birth.location.lng',location.lng ?? ''))}"></label>
      <label>纬度<input id="profileLat" type="number" min="-90" max="90" step="any" required value="${esc(read('birth.location.lat',location.lat ?? ''))}"></label>
      <label>出生地 UTC 偏移（小时）<input id="profileTimezone" type="number" min="-12" max="14" step="0.25" required value="${esc(read('birth.timezone_offset',birth.timezone_offset ?? ''))}"></label>
      <label>出生地时区<input id="profileIana" maxlength="100" list="profileIanaChoices" required placeholder="如 Asia/Shanghai（中国标准时间）" value="${esc(read('birth.location.tz',location.tz || ''))}"><datalist id="profileIanaChoices"><option value="Asia/Shanghai">中国标准时间</option><option value="Asia/Tokyo">日本</option><option value="America/New_York">美国纽约</option><option value="Europe/London">英国伦敦</option></datalist></label>
      <label>出生记录的时间依据<select id="profileClockBasis" required><option value="">请核对记录依据</option><option value="clock">当地钟表时间（含当时夏令时）</option><option value="standard">当地标准时间（不含夏令时）</option><option value="unknown">记录依据不确定</option></select></label>
    </div><p class="muted">时刻未知时，只记录日期；计算将标明候选时刻样本与不确定范围，不把样本当作你的出生时刻。</p><label class="profile-consent"><input id="profileConsent" type="checkbox" required> 我已核对以上资料，明确授权保存为我的出生与性别资料，并用于后续排盘。</label><button class="btn-gold" type="submit">确认并保存资料</button><p id="profileStatus" role="status" aria-live="polite"></p></form>`;
    $('#profileGender').value=read('gender',candidate.gender || '');$('#profilePrecision').value=['exact','approximate','unknown'].includes(precision)?precision:'exact';
    $('#profileClockBasis').value=read('birth.clock_basis',birth.clock_basis || '');
    const update=()=>{const value=$('#profilePrecision').value;$('#profileTime').disabled=value==='unknown';$('#profileTime').required=value!=='unknown';$('#profileUncertaintyLabel').classList.toggle('hidden',value!=='approximate');$('#profileUncertainty').required=value==='approximate';};
    $('#profilePrecision').onchange=update;update();
    $('#profileForm').onsubmit=async event=>{event.preventDefault();const form=event.target;if(!form.reportValidity())return;const button=form.querySelector('button'),status=$('#profileStatus');button.disabled=true;
      try{const precision=$('#profilePrecision').value,solar=$('#profileDate').value+(precision==='unknown'?'':' '+$('#profileTime').value),profile={gender:$('#profileGender').value,birth:{solar_datetime:solar,precision,time_unknown:precision==='unknown',time_uncertainty_minutes:precision==='approximate'?Number($('#profileUncertainty').value):0,timezone_offset:Number($('#profileTimezone').value),clock_basis:$('#profileClockBasis').value,location:{city:$('#profileCity').value.trim(),lng:Number($('#profileLng').value),lat:Number($('#profileLat').value),tz:$('#profileIana').value.trim()}}};
        const result=await writeJson('/api/subjects/self/profile/confirm',{confirmed:$('#profileConsent').checked,expected_revision:snapshot.revision,profile});
        const saved=tarotList(result.receipts).filter(r=>r.write_status==='saved');status.textContent=saved.length?'已保存 '+saved.length+' 项你确认的资料。':'本次未收到保存成功回执，请核对后再试。';
        if(saved.length){loaded.chart=false;ziweiLoaded=false;astroLoaded=false;loaded.memory=false;await refreshLinkedCharts();$('#profileConsent').checked=false;snapshot.revision=(await apiJson('/api/subjects/self/profile')).revision;}
      }catch(e){status.textContent='资料尚未保存：'+e.message;}finally{button.disabled=false;}
    };
  }catch(e){root.innerHTML=errState('档案暂时无法读取：'+e.message,'loadProfile');}finally{delete root.dataset.loading;}
}
$('#profilePanel').addEventListener('toggle',()=>{if($('#profilePanel').open && !$('#profileForm') && !$('#profileRoot').dataset.loading)loadProfile();});
async function loadSidebar() {
  try {
    const arc = await apiJson("/api/archive");
    const pillars = (((arc || {}).charts || {}).bazi || {}).pillars || {};
    const labels = [["year", "年"], ["month", "月"], ["day", "日"], ["hour", "时"]];
    const cells = labels.map(([k, zh]) => {
      const p = pillars[k];
      const gz = typeof p === "string" ? p : (p && p.ganzhi) || "—";
      const wx = typeof p === "object" && p ? (p.wuxing_gan || "") : "";
      return `<div>
        <div class="pillar-label mb-1">${zh}</div>
        <div class="font-serif text-lg font-bold" style="color:${wxColor(wx)}">${esc(gz)}</div>
      </div>`;
    }).join("");
    $("#miniPillars").innerHTML = cells || `<div class="col-span-4 text-xs text-gray-600">尚未建档</div>`;
    const cal = (arc || {}).calibration || {};
    const bias = cal.timing_bias || "暂无记录";
    const dm = ((((arc || {}).charts || {}).bazi || {}).day_master) || "";
    $("#miniMeta").innerHTML = `
      ${dm ? `<div>日主：<span class="gold-text">${esc(dm)}</span></div>` : ""}
      <div>应期偏差：<span class="text-gray-300">${esc(bias)}</span></div>
      <div>近期经历与个人记忆会作为解读参考</div>`;
  } catch (e) {
    if (e.status !== 401) {
      $("#miniPillars").innerHTML = `<div class="col-span-4 text-xs text-gray-600">档案读取失败</div>`;
      $("#miniMeta").innerHTML = `<div class="text-xs text-gray-600">${esc(e.message || e)}</div>`;
    }
  }
}

/* ================= ② 命盘 ================= */
let chartData = null;
const chartRequests={bazi:0,ziwei:0,astro:0};
async function loadChart() {
  const request=++chartRequests.bazi,date=chartDate();
  const root = $("#chartRoot");
  root.innerHTML = `<div class="text-center text-gray-500 text-sm py-16">排盘数据加载中…</div>`;
  let c;
  try { c = await apiJson("/api/chart?date=" + date); }
  catch (e) {
    if(request!==chartRequests.bazi)return;
    if ([400,422].includes(e.status)) {
      root.innerHTML = emptyState("命", "尚未建档",
        e.message)+`<button class="quiet-button" onclick="openProfile()">核对并确认出生资料</button>`;
    } else if (e.status !== 401) {
      root.innerHTML = errState("命盘加载失败：" + (e.message || e), "loadChart");
    }
    return;
  }
  if(request!==chartRequests.bazi)return;
  if (!$("#analysisDate").value) $("#analysisDate").value = date;
  c.liuyue=c.target_liuyue || c.liuyue;
  chartData = c;
  root.innerHTML = chartMetadata(c)+renderChart(c);
}
function chartMetadata(c) {
  const meta=c.core_meta;if(!meta)return '';
  const branches=tarotList(meta.branches),profiles=Object.values(meta.profiles || {}),sampled=branches.some(b=>b.coverage!=='exact_input');
  const notes=[...tarotList(meta.warnings),...profiles.flatMap(p=>tarotList(p.warnings))];
  return `${sampled?'<p class="chart-sample-notice" role="status">出生时刻存在不确定性：当前盘面是候选样本之一。样本间相同的结果也不表示整个区间都成立。</p>':''}<details class="chart-method"><summary>排盘口径与出生时刻范围</summary>${branches.map(b=>`<p>${b.coverage==='exact_input'?'记录的出生时刻':'候选时刻样本'}：${esc(b.civil_datetime)}${b.sampling_range?' · 范围 '+esc(b.sampling_range.start)+' 至 '+esc(b.sampling_range.end):''}</p>`).join('')}${profiles.map(p=>`<p>流派：${esc(p.school_id)}</p><pre>${esc(JSON.stringify({采用口径:p.actual_method,引擎版本:p.versions},null,2))}</pre>${calculationFallbackHtml(p.fallback)}`).join('')}${[...new Set(notes)].map(n=>`<p>${esc(n)}</p>`).join('')}</details>`;
}
function renderChart(c) {
  c = c || {};
  const P = c.pillars || {};
  const labels = [["year", "年柱"], ["month", "月柱"], ["day", "日柱"], ["hour", "时柱"]];
  const pillarCards = labels.map(([k, zh]) => {
    const p = P[k];
    if (!p) return `<div class="glass p-4 text-center text-gray-600 text-sm">${zh}<br>—</div>`;
    const gan = p.gan || (p.ganzhi || "")[0] || "—";
    const zhi = p.zhi || (p.ganzhi || "")[1] || "—";
    return `<div class="glass glass-hover chart-click p-4 text-center" onclick="openPillarDetail('${k}')" title="点击查看${zh}详情">
      <div class="pillar-label mb-2">${zh}</div>
      <div class="ganzhi-big" style="color:${wxColor(p.wuxing_gan)}">${esc(gan)}</div>
      <div class="ganzhi-big" style="color:${wxColor(p.wuxing_zhi)}">${esc(zhi)}</div>
      <div class="mt-2 text-xs space-y-1 text-gray-400">
        ${p.shishen_gan ? `<div>${esc(p.shishen_gan)} · ${esc(p.wuxing_gan || "")}</div>` : ""}
        ${p.shishen_zhi ? `<div>${esc(p.shishen_zhi)} · ${esc(p.wuxing_zhi || "")}</div>` : ""}
        ${p.nayin ? `<div class="text-gray-500">纳音 ${esc(p.nayin)}</div>` : ""}
      </div>
    </div>`;
  }).join("");

  const wc = c.wuxing_count || {};
  const wxOrder = ["金", "木", "水", "火", "土"];
  const wxTotal = wxOrder.reduce((s, k) => s + (Number(wc[k]) || 0), 0) || 1;
  const wxBars = wxOrder.map(k => {
    const n = Number(wc[k]) || 0;
    const pct = Math.round(n / wxTotal * 100);
    return `<div class="flex items-center gap-3">
      <div class="w-6 text-sm font-serif font-bold" style="color:${wxColor(k)}">${k}</div>
      <div class="bar-track flex-1"><div class="bar-fill" style="width:${pct}%;background:${wxColor(k)}"></div></div>
      <div class="w-8 text-right text-xs text-gray-400">${n}</div>
    </div>`;
  }).join("");

  const nowY = Number(chartDate().slice(0,4));
  const dayun = Array.isArray(c.dayun) ? c.dayun : [];
  const dayunBar = dayun.length ? `<div class="flex gap-1.5 overflow-x-auto pb-1">` + dayun.map((d, i) => {
    const cur = nowY >= (d.start_year || 0) && nowY <= (d.end_year || 0);
    return `<div class="dayun-seg chart-click ${cur ? "now" : ""}" style="min-width:86px" title="${d.start_year || "?"}–${d.end_year || "?"} · 点击查看" onclick="openDayunDetail(${i})">
      <div><div class="font-serif font-bold">${esc(d.ganzhi || "—")}</div>
      <div class="text-[10px] opacity-70">${d.start_age != null ? d.start_age + "岁起" : ""}</div></div>
    </div>`;
  }).join("") + `</div>` : `<div class="text-xs text-gray-600">暂无大运数据</div>`;

  const nowM = chartDate().slice(0, 7);
  const liunian = Array.isArray(c.liunian) ? c.liunian : [];
  const liuyue = Array.isArray(c.liuyue) ? c.liuyue : [];
  const liunianHtml = liunian.length ? `<div class="flex flex-wrap gap-2">` + liunian.map((y, i) =>
    `<span class="badge chart-click ${y.year === nowY ? "badge-gold" : "badge-gray"}" onclick="openLiunianDetail(${i})" title="点击查看">${esc(y.year)} ${esc(y.ganzhi || "")}</span>`
  ).join("") + `</div>` : `<div class="text-xs text-gray-600">暂无流年数据</div>`;
  const liuyueHtml = liuyue.length ? `<div class="flex flex-wrap gap-2">` + liuyue.map((m, i) =>
    `<span class="badge chart-click ${m.month === nowM ? "badge-gold" : "badge-gray"}" onclick="openLiuyueDetail(${i})" title="点击查看">${esc((m.month || "").slice(5))}月 ${esc(m.ganzhi || "")}</span>`
  ).join("") + `</div>` : `<div class="text-xs text-gray-600">暂无流月数据</div>`;

  const xys = Array.isArray(c.xiyongshen) ? c.xiyongshen : [];
  return `
  <div class="space-y-4">
    <div class="glass p-4 flex flex-wrap items-center gap-x-6 gap-y-2">
      <div><span class="text-xs text-gray-500">阳历</span> <span class="text-gray-200">${esc(c.solar_datetime || "—")}</span></div>
      <div><span class="text-xs text-gray-500">农历</span> <span class="text-gray-200">${esc(c.lunar_datetime || "—")}</span></div>
      ${c.day_master ? `<div><span class="text-xs text-gray-500">日主</span>
        <span class="font-serif font-bold" style="color:${wxColor(c.day_master_wuxing)}">${esc(c.day_master)}</span>
        <span class="text-xs text-gray-400">${esc(c.day_master_wuxing || "")}</span></div>` : ""}
      ${xys.length ? `<div><span class="text-xs text-gray-500">生扶与克泄提示（启发式）</span>
        ${xys.map(x => `<span class="badge ml-1" style="color:${wxColor(x)};border-color:${wxColor(x)}55;background:${wxColor(x)}14">${esc(x)}</span>`).join("")}</div>` : ""}
    </div>
    ${xys.length?'<p class="muted">旧字段“喜用神”按五行计数粗分生扶与克泄耗，数量持平时参考月令五行；尚未完成旺衰、格局与调候的完整论证。</p>':''}
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">${pillarCards}</div>
    <div class="grid md:grid-cols-2 gap-4">
      <div class="glass min-w-0 p-4">
        <div class="text-xs tracking-widest text-gray-500 mb-3">五 行 构 成 计 数</div>
        <div class="space-y-2.5">${wxBars}</div>
        <p class="muted chart-count-note">按四柱天干与地支主气各计一份；没有藏干、月令与旺衰权重，条形占比仅表示数量构成。</p>
      </div>
      <div class="glass min-w-0 p-4">
        <div class="text-xs tracking-widest text-gray-500 mb-3">大 运（当前高亮 · 点击查看）</div>
        ${dayunBar}
      </div>
    </div>
    <div class="glass p-4">
      <details class="fold" open><summary>流年（前后十年，当前年鎏金 · 点击查看）</summary><div class="pt-2">${liunianHtml}</div></details>
      <details class="fold"><summary>流月（所选年份，按月中样本计算 · 点击查看）</summary><div class="pt-2">${liuyueHtml}</div></details>
    </div>
  </div>`;
}

/* ---- 命盘元素点击详情：数据全部来自已加载的 /api/chart（chartData），不发额外请求 ---- */
const GAN_WX = { "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土", "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水" };
const GAN_YY = { "甲": 1, "丙": 1, "戊": 1, "庚": 1, "壬": 1, "乙": 0, "丁": 0, "己": 0, "辛": 0, "癸": 0 }; // 1=阳 0=阴
const ZHI_WX = { "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水" };
const WX_SHENG = { "木": "火", "火": "土", "土": "金", "金": "水", "水": "木" }; // 我生
const WX_KE    = { "木": "土", "土": "水", "水": "火", "火": "金", "金": "木" }; // 我克
/* 以日主天干为基准推导目标天干的十神：同我比劫、我生食伤、生我为印、我克为财、克我为官杀；同性取偏（比肩/食神/偏印/偏财/七杀），异性取正（劫财/伤官/正印/正财/正官） */
function shishenOf(dmGan, gan) {
  const dw = GAN_WX[dmGan], tw = GAN_WX[gan];
  if (!dw || !tw) return "";
  const same = GAN_YY[dmGan] === GAN_YY[gan];
  if (dw === tw) return same ? "比肩" : "劫财";
  if (WX_SHENG[dw] === tw) return same ? "食神" : "伤官";
  if (WX_SHENG[tw] === dw) return same ? "偏印" : "正印";
  if (WX_KE[dw] === tw) return same ? "偏财" : "正财";
  return same ? "七杀" : "正官";
}
function dayMasterGan() { return String((chartData || {}).day_master || "").trim()[0] || ""; }
/* 「丙火对甲木日主为「食神」」式的一句话；字段不足时返回空串 */
function relationLine(gan) {
  const dm = dayMasterGan();
  const ss = dm && gan ? shishenOf(dm, gan) : "";
  return ss ? `${gan}${GAN_WX[gan]}对${dm}${GAN_WX[dm]}日主为「${ss}」` : "";
}
const PILLAR_DESC = { year: "年柱代表祖辈与童年", month: "月柱代表父母与青年", day: "日柱代表自己与配偶", hour: "时柱代表子女与晚年" };
/* 复用时间轴的抽屉组件 */
function openChartDrawer(html) {
  rememberFocus('drawer');
  $("#drawer").innerHTML = html;
  $("#drawerMask").classList.remove("hidden");
  requestAnimationFrame(() => {$("#drawer").classList.add("open");$("#drawer").querySelector("button")?.focus();});
}
function chartDrawerHead(title, sub) {
  return `<div class="flex items-start justify-between mb-4">
    <div>
      <div class="font-serif text-lg gold-text">${esc(title)}</div>
      ${sub ? `<div class="text-xs text-gray-500 mt-1">${esc(sub)}</div>` : ""}
    </div>
    <button class="text-gray-500 hover:text-gray-300 text-xl leading-none px-2" onclick="closeDrawer()">×</button>
  </div>`;
}
function infoRow(k, v) {
  return v ? `<div class="flex justify-between gap-3"><span class="text-gray-500 shrink-0">${esc(k)}</span><span class="text-right">${v}</span></div>` : "";
}
function aiAskBtn(q) {
  return `<button class="btn-gold w-full py-2.5 text-sm mt-5" onclick="askAiAbout(${jsArg(q)})">让 AI 深入解读</button>`;
}
function askAiAbout(q) {
  closeDrawer();
  switchPage("chat");
  sendChat(q, {system:"bazi",key:q.slice(0,100),date:chartDate(),focus:analysisFocus()});
}
function bigGanzhiHtml(gz, wxGan, wxZhi) {
  const gan = gz[0] || "—", zhi = gz[1] || "—";
  return `<div class="glass p-4 text-center mb-4">
    <div class="ganzhi-big" style="color:${wxColor(wxGan || GAN_WX[gan])}">${esc(gan)}</div>
    <div class="ganzhi-big" style="color:${wxColor(wxZhi || ZHI_WX[zhi])}">${esc(zhi)}</div>
  </div>`;
}
function gzWuxingDesc(gz) {
  const gan = gz[0] || "", zhi = gz[1] || "";
  return [gan && GAN_WX[gan] ? `天干${gan}·五行属${GAN_WX[gan]}` : "",
          zhi && ZHI_WX[zhi] ? `地支${zhi}·五行属${ZHI_WX[zhi]}` : ""].filter(Boolean).join("，");
}
function openPillarDetail(k) {
  const p = (((chartData || {}).pillars || {})[k]) || {};
  const zh = { year: "年柱", month: "月柱", day: "日柱", hour: "时柱" }[k] || k;
  const gz = p.ganzhi || ((p.gan || "") + (p.zhi || ""));
  const gan = p.gan || gz[0] || "—";
  const zhi = p.zhi || gz[1] || "—";
  openChartDrawer(`
    ${chartDrawerHead(zh + (gz ? " · " + gz : ""), PILLAR_DESC[k] || "")}
    ${bigGanzhiHtml(gz, p.wuxing_gan, p.wuxing_zhi)}
    <div class="glass p-4 text-sm space-y-2">
      ${infoRow("天干", `${esc(gan)}${p.wuxing_gan ? ` · 五行属${esc(p.wuxing_gan)}` : ""}${p.shishen_gan ? ` · ${esc(p.shishen_gan)}` : ""}`)}
      ${infoRow("地支", `${esc(zhi)}${p.wuxing_zhi ? ` · 五行属${esc(p.wuxing_zhi)}` : ""}${p.shishen_zhi ? ` · ${esc(p.shishen_zhi)}` : ""}`)}
      ${infoRow("纳音", esc(p.nayin || ""))}
    </div>
    ${aiAskBtn(`请解读我命盘的${zh}${gz}`)}`);
}
function openDayunDetail(i) {
  const d = (((chartData || {}).dayun) || [])[i];
  if (!d) return;
  const gz = d.ganzhi || "";
  const nowY = Number(chartDate().slice(0,4));
  let rel = "";
  if (d.start_year != null && d.end_year != null) {
    if (nowY >= d.start_year && nowY <= d.end_year) rel = "当前大运";
    else if (nowY < d.start_year) rel = (d.start_year - nowY) + "年后进入";
    else rel = "已过去";
  }
  const years = (d.start_year != null && d.end_year != null) ? `${d.start_year}–${d.end_year}` : "";
  let ages = "";
  if (d.start_age != null) {
    ages = d.start_age + "岁起";
    if (d.start_year != null && d.end_year != null) ages = `${d.start_age}–${d.start_age + (d.end_year - d.start_year)}岁`;
  }
  openChartDrawer(`
    ${chartDrawerHead("大运 · " + (gz || "—"), rel)}
    ${bigGanzhiHtml(gz)}
    <div class="glass p-4 text-sm space-y-2">
      ${infoRow("干支", esc(gz))}
      ${infoRow("起止年份", esc(years))}
      ${infoRow("起止年龄", esc(ages))}
      ${infoRow("五行", esc(gzWuxingDesc(gz)))}
      ${infoRow("与现在关系", esc(rel))}
    </div>
    ${aiAskBtn(`请解读我的${gz}大运${years ? `（${years}年）` : ""}`)}`);
}
function openLiunianDetail(i) {
  const y = (((chartData || {}).liunian) || [])[i];
  if (!y) return;
  const gz = y.ganzhi || "";
  openChartDrawer(`
    ${chartDrawerHead(`流年 · ${y.year ?? "—"}${gz ? " " + gz : ""}`, y.year === new Date().getFullYear() ? "今年" : "")}
    ${bigGanzhiHtml(gz)}
    <div class="glass p-4 text-sm space-y-2">
      ${infoRow("年份", esc(y.year ?? ""))}
      ${infoRow("干支", esc(gzWuxingDesc(gz) || gz))}
      ${infoRow("与日主关系", esc(relationLine(gz[0] || "")))}
    </div>
    ${aiAskBtn(`请解读我 ${y.year} ${gz}流年`)}`);
}
function fmtMonthCn(m) {
  const mm = /^(\d{4})-(\d{2})$/.exec(String(m || ""));
  return mm ? `${mm[1]}年${Number(mm[2])}月` : String(m || "");
}
function openLiuyueDetail(i) {
  const m = (((chartData || {}).liuyue) || [])[i];
  if (!m) return;
  const gz = m.ganzhi || "";
  const label = fmtMonthCn(m.month);
  openChartDrawer(`
    ${chartDrawerHead(`流月 · ${label}${gz ? " " + gz : ""}`, m.month === new Date().toISOString().slice(0, 7) ? "本月" : "")}
    ${bigGanzhiHtml(gz)}
    <div class="glass p-4 text-sm space-y-2">
      ${infoRow("月份", esc(label))}
      ${infoRow("干支", esc(gzWuxingDesc(gz) || gz))}
      ${infoRow("与日主关系", esc(relationLine(gz[0] || "")))}
    </div>
    ${aiAskBtn(`请解读我 ${label} ${gz}流月`)}`);
}

/* ================= ②b 命盘 · 紫微 tab（v2.1，懒加载） ================= */
let ziweiData = null, ziweiLoaded = false, ziweiLoading = false;
function switchChartTab(name) {
  $$("#chartTabs .nav-tab").forEach(t => t.classList.toggle("active", t.dataset.chart === name));
  $("#chartPaneBazi").classList.toggle("hidden", name !== "bazi");
  $("#chartPaneZiwei").classList.toggle("hidden", name !== "ziwei");
  $("#chartPaneAstro").classList.toggle("hidden", name !== "astro");
  if (name === "ziwei" && !ziweiLoaded && !ziweiLoading) loadZiwei();  // 首次点击才请求
  if (name === "astro" && !astroLoaded && !astroLoading) loadAstro();
}
$$("#chartTabs .nav-tab").forEach(t => t.addEventListener("click", () => switchChartTab(t.dataset.chart)));

async function loadZiwei() {
  const request=++chartRequests.ziwei,date=chartDate();
  const root = $("#ziweiRoot");
  ziweiLoading = true;
  root.innerHTML = `<div class="text-center text-gray-500 text-sm py-16">紫微排盘数据加载中…</div>`;
  let c;
  try { c = await apiJson("/api/chart_ziwei?date=" + date); }
  catch (e) {
    if(request!==chartRequests.ziwei)return;
    ziweiLoading = false;
    if (e.status === 400) {
      root.innerHTML = emptyState("微", "尚未建档",
        "请先在飞书 / CLI 对 Agent 说「开始排盘」完成建档，再回来查看紫微命盘。");
    } else if (e.status !== 401) {
      root.innerHTML = errState("紫微命盘加载失败：" + (e.message || e), "loadZiwei");
    }
    return;  // 401：口令模态框已弹出，ziweiLoaded 保持 false，重新点击 tab 即重试
  }
  if(request!==chartRequests.ziwei)return;
  ziweiData = c; ziweiLoaded = true; ziweiLoading = false;
  root.innerHTML = chartMetadata(c)+renderZiwei(c);
}

/* 地支 → 传统掌上排盘 4×4 格位（巳午未申在上排，寅丑子亥在下排） */
const ZW_AREA = { "巳": "si", "午": "wu", "未": "wei", "申": "shen", "辰": "chen", "酉": "you",
                  "卯": "mao", "戌": "xu", "寅": "yin", "丑": "chou", "子": "zi", "亥": "hai" };
const ZW_BRIGHT_C = { "庙": "#C9A96A", "旺": "#D8C295", "得": "#D8DCE8", "利": "#D8DCE8", "平": "#9AA1B5", "不": "#8A90A2", "陷": "#787C8A" };
function zwStarHtml(s) {
  const color = ZW_BRIGHT_C[s.brightness] || "#D8DCE8";
  const br = s.brightness ? `<span class="zw-bright">${esc(s.brightness)}</span>` : "";
  const mut = s.mutagen ? `<span class="zw-mut" title="生年四化：化${esc(s.mutagen)}">${esc(s.mutagen)}</span>` : "";
  return `<span class="zw-star" style="color:${color}">${esc(s.name)}</span>${br}${mut}`;
}
function zwPalaceBadges(p) {
  let b = "";
  if (p.name === "命宫") b += `<span class="badge badge-gold">命宫</span>`;
  if (p.is_body) b += `<span class="badge badge-purple">身宫</span>`;
  if (p.is_laiyin) b += `<span class="badge badge-gray">来因</span>`;
  return b ? `<span class="inline-flex gap-1 flex-wrap">${b}</span>` : "";
}
/* 虚岁 = 当前年 - 出生年 + 1；出生年取自 corrected_time（地方平太阳时） */
function currentNominalAge(c) {
  const by = Number(String((c || {}).corrected_time || "").slice(0, 4));
  return by ? Number(chartDate().slice(0,4)) - by + 1 : 0;
}
function zwDecadalNow(p, age) {
  const dr = (p.decadal && p.decadal.range) || [];
  return !!(age && dr.length === 2 && age >= dr[0] && age <= dr[1]);
}
function renderZiwei(c) {
  c = c || {};
  const palaces = Array.isArray(c.palaces) ? c.palaces : [];
  if (!palaces.length) return emptyState("微", "紫微排盘数据为空", "服务端 ziwei.py 未返回宫位数据。");
  const age = currentNominalAge(c);
  const findPalace = pred => palaces.find(pred) || null;
  const mingP = findPalace(p => p.name === "命宫");
  const bodyP = findPalace(p => p.is_body);
  const laiyinP = findPalace(p => p.is_laiyin);
  const nowP = findPalace(p => zwDecadalNow(p, age));

  const cells = palaces.map((p, i) => {
    const branch = String(p.ganzhi || "")[1] || "";
    const area = ZW_AREA[branch];
    const dr = (p.decadal && p.decadal.range) || [];
    const major = (Array.isArray(p.major) ? p.major : []).map(s => `<div>${zwStarHtml(s)}</div>`).join("");
    const minor = (Array.isArray(p.minor) ? p.minor : []).map(s => zwStarHtml(s)).join(" · ");
    return `<div class="zw-cell chart-click ${zwDecadalNow(p, age) ? "zw-now" : ""}" ${area ? `style="grid-area:${area}"` : ""}
      onclick="openPalaceDetail(${i})" title="点击查看${esc(p.name || "")}详情">
      <div class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 mb-1.5">
        <span class="zw-pname">${esc(p.name || "—")}</span>${zwPalaceBadges(p)}
        <span class="text-[10px] text-gray-500 ml-auto shrink-0">${dr.length === 2 ? `${dr[0]}–${dr[1]}` : ""}</span>
      </div>
      <div class="space-y-0.5">${major}</div>
      ${minor ? `<div class="text-[10px] text-gray-500 leading-relaxed mt-1">${minor}</div>` : ""}
      <div class="text-right text-xs text-gray-500 mt-auto pt-1">${esc(p.ganzhi || "")}</div>
    </div>`;
  }).join("");

  const center = `<div class="zw-center" style="grid-area:center">
    <div class="font-serif gold-text text-center text-xl font-bold mb-2">${esc(c.wuxing_ju || "—")}</div>
    <div class="text-xs text-gray-400 space-y-1.5">
      ${infoRow("农历", esc(c.lunar_date || ""))}
      ${infoRow("地方平太阳时", esc(c.corrected_time || ""))}
      ${infoRow("生肖 / 星座", `${esc(c.zodiac || "—")} · ${esc(c.sign || "—")}`)}
      ${infoRow("命主 / 身主", `${esc(c.ming_zhu || "—")} · ${esc(c.shen_zhu || "—")}`)}
    </div>
    <div class="mt-3 pt-2 text-[11px] text-gray-500 space-y-1" style="border-top:1px solid rgba(255,255,255,.06)">
      <div><span class="badge badge-gold">命宫</span> 鎏金 · <span class="badge badge-purple">身宫</span> 紫微紫 · <span class="badge badge-gray">来因</span> 灰</div>
      <div>鎏金小标 = 生年四化（禄/权/科/忌）· 金框宫 = 当前大限</div>
    </div>
  </div>`;

  return `
  <div class="space-y-4">
    <div class="glass p-4 flex flex-wrap items-center gap-x-6 gap-y-2">
      <div><span class="text-xs text-gray-500">五行局</span> <span class="font-serif font-bold gold-text">${esc(c.wuxing_ju || "—")}</span></div>
      <div><span class="text-xs text-gray-500">命主</span> <span class="font-serif font-bold text-gray-100">${esc(c.ming_zhu || "—")}</span></div>
      <div><span class="text-xs text-gray-500">身主</span> <span class="font-serif font-bold text-gray-100">${esc(c.shen_zhu || "—")}</span></div>
      ${mingP ? `<div><span class="text-xs text-gray-500">命宫</span> <span class="gold-text">${esc(mingP.ganzhi || "")}</span></div>` : ""}
      ${bodyP ? `<div><span class="text-xs text-gray-500">身宫</span> <span class="ziwei-text">${esc(bodyP.name || "")} ${esc(bodyP.ganzhi || "")}</span></div>` : ""}
      ${laiyinP ? `<div><span class="text-xs text-gray-500">来因宫</span> <span class="text-gray-300">${esc(laiyinP.name || "")} ${esc(laiyinP.ganzhi || "")}</span></div>` : ""}
      ${nowP ? `<div><span class="text-xs text-gray-500">当前大限</span> <span class="gold-text">${esc(nowP.name || "")} ${esc((nowP.decadal || {}).ganzhi || "")}</span><span class="text-xs text-gray-500">（虚岁 ${age}）</span></div>` : ""}
    </div>
    <div class="overflow-x-auto pb-1">
      <div class="zw-grid">${cells}${center}</div>
    </div>
    <div class="text-[11px] text-gray-600 px-1">点击宫格查看主星 / 副星 / 大限详情；星曜颜色按亮度（庙旺鎏金，平陷灰）。</div>
  </div>`;
}

/* 宫格详情：复用抽屉组件，数据来自已加载的 ziweiData，不发额外请求 */
function openPalaceDetail(i) {
  const p = (((ziweiData || {}).palaces) || [])[i];
  if (!p) return;
  const dr = (p.decadal && p.decadal.range) || [];
  const dg = (p.decadal && p.decadal.ganzhi) || "";
  const age = currentNominalAge(ziweiData);
  const isNow = zwDecadalNow(p, age);
  const major = Array.isArray(p.major) ? p.major : [];
  const minor = Array.isArray(p.minor) ? p.minor : [];
  const ages = Array.isArray(p.ages) ? p.ages : [];
  const starRows = arr => arr.map(s => `
    <div class="flex items-center justify-between gap-2 py-1.5" style="border-bottom:1px solid rgba(255,255,255,.05)">
      <span>${zwStarHtml(s)}</span>
      <span class="text-xs text-gray-500 shrink-0">${esc(s.brightness || "")}${s.mutagen ? ` · 化${esc(s.mutagen)}` : ""}</span>
    </div>`).join("");
  const sub = [p.is_body ? "身宫在此" : "", p.is_laiyin ? "来因宫（生年干所在宫）" : ""].filter(Boolean).join(" · ");
  openChartDrawer(`
    ${chartDrawerHead(`${p.name || "—"} · ${p.ganzhi || ""}`, sub)}
    ${zwPalaceBadges(p) ? `<div class="flex gap-2 mb-4">${zwPalaceBadges(p)}</div>` : ""}
    <div class="glass p-4 text-sm space-y-2 mb-4">
      ${infoRow("宫位干支", esc(gzWuxingDesc(p.ganzhi || "") || p.ganzhi || ""))}
      ${dr.length === 2 ? infoRow("大限区间", esc(`${dr[0]}–${dr[1]} 岁（虚岁）${dg ? " · " + dg : ""}`)) : ""}
      ${isNow ? infoRow("与现在关系", `<span class="gold-text">当前大限（虚岁 ${age}）</span>`) : ""}
      ${ages.length ? infoRow("小限年龄", esc(ages.join("、"))) : ""}
    </div>
    ${major.length ? `<div class="text-xs tracking-widest text-gray-500 mb-2">主 星（亮度 · 四化）</div><div class="glass p-3 text-sm mb-4">${starRows(major)}</div>` : ""}
    ${minor.length ? `<div class="text-xs tracking-widest text-gray-500 mb-2">副 星</div><div class="glass p-3 text-sm mb-2">${starRows(minor)}</div>` : ""}
    ${renderZiweiLinks(p)}
    <button class="btn-gold w-full py-2.5 text-sm mt-5" onclick="askLinked('ziwei',${i},${jsArg('紫微'+p.name)})">让 AI 解读此宫</button>`);
}

/* ================= ②c 命盘 · 星盘 tab（v2.2，懒加载） ================= */
let astroData = null, astroLoaded = false, astroLoading = false;
async function loadAstro() {
  const request=++chartRequests.astro,date=chartDate();
  const root = $("#astroRoot");
  astroLoading = true;
  root.innerHTML = `<div class="text-center text-gray-500 text-sm py-16">星盘数据加载中…</div>`;
  let c;
  try { c = await apiJson("/api/chart_astro?date=" + date); }
  catch (e) {
    if(request!==chartRequests.astro)return;
    astroLoading = false;
    if (e.status === 400) {
      root.innerHTML = emptyState("星", "尚未建档",
        "请先在飞书 / CLI 对 Agent 说「开始排盘」完成建档，再回来查看星盘。");
    } else if (e.status !== 401) {
      root.innerHTML = errState("星盘加载失败：" + (e.message || e), "loadAstro");
    }
    return;  // 401：口令模态框已弹出，astroLoaded 保持 false，重新点击 tab 即重试
  }
  if(request!==chartRequests.astro)return;
  astroData = c; astroLoaded = true; astroLoading = false;
  root.innerHTML = chartMetadata(c)+renderAstro(c);
}

/* 十二星座 → 四象 → 配色（火红 / 土金 / 风紫 / 水蓝） */
const SIGN_ELEM = { "白羊": "火", "狮子": "火", "射手": "火",
                    "金牛": "土", "处女": "土", "摩羯": "土",
                    "双子": "风", "天秤": "风", "水瓶": "风",
                    "巨蟹": "水", "天蝎": "水", "双鱼": "水" };
const ELEM_COLOR = { "火": "#E07A5F", "土": "#C9A96A", "风": "#8B7CF6", "水": "#6EA8D8" };
function signColor(sign) { return ELEM_COLOR[SIGN_ELEM[sign]] || "#D8DCE8"; }
const ASTRO_FULL = { "天王": "天王星", "海王": "海王星", "冥王": "冥王星" };
const ASTRO_ORDER = ["太阳", "月亮", "水星", "金星", "火星", "木星", "土星", "天王", "海王", "冥王"];
/* 本命静态白话（写死，与档案星盘一致；行星名 → 一句话） */
const ASTRO_DESC = {
  "太阳": "务实稳定、重视物质安全感",
  "月亮": "情绪需要和谐与人际认可",
  "水星": "思维直来直去、表达快人快语",
  "金星": "喜欢新鲜有趣的互动，聊得来才有感觉",
  "火星": "行动讲方法重细节、做事精益求精",
  "木星": "幸运来自稳健积累，对物质好运有体感",
  "土星": "在人际与合作中学会责任与边界",
  "天王": "骨子里有股破旧立新的冲劲",
  "海王": "想象力与共情力丰沛、容易理想化",
  "冥王": "对目标与秩序有深层的执着与蜕变力",
  "asc":  "给人的第一印象大方自信、自带舞台感",
  "mc":   "事业追求稳扎稳打、以实绩赢得认可"
};
function astroPlanetCard(name, p, big) {
  const color = signColor(p.sign);
  return `<div class="glass glass-hover chart-click p-4 text-center ${big ? "astro-big" : ""}" onclick="openAstroDetail(${jsArg('p:'+name)})" title="点击查看${esc(name)}详情">
    <div class="pillar-label mb-1">${esc(name)}</div>
    <div class="font-serif ${big ? "text-xl" : ""} font-bold" style="color:${color}">${esc(p.sign)}${SIGN_ELEM[p.sign] ? `<span class="text-[10px] font-normal opacity-70 ml-1">${SIGN_ELEM[p.sign]}</span>` : ""}</div>
    <div class="astro-deg ${big ? "astro-deg-big" : ""}" style="color:${color}">${p.deg}°</div>
  </div>`;
}
function renderAstro(c) {
  c = c || {};
  const planets = c.planets || {};
  const names = ASTRO_ORDER.filter(n => planets[n]);
  if (!names.length) return emptyState("星", "星盘数据为空", "服务端 astro.py 未返回行星数据。");
  const angleCard = (key, label, v, hlClass) => v ? `
    <div class="glass astro-angle p-4 text-center" onclick="openAstroDetail('${key}')" title="点击查看${label}详情">
      <div class="pillar-label mb-1">${label}</div>
      <div class="font-serif text-xl font-bold ${hlClass}">${esc(v.sign)}</div>
      <div class="astro-deg ${hlClass}">${v.deg}°</div>
    </div>` : "";
  const infoBar = `
    <div class="grid grid-cols-3 gap-3">
      <div class="glass p-4 text-center">
        <div class="pillar-label mb-1">出生民用时间</div>
        <div class="font-serif font-bold text-gray-100 text-sm md:text-base mt-2">${esc(c.civil_time || c.corrected_time || "—")}</div>
        <div class="text-[10px] text-gray-500 mt-1">民用时间 → UTC · Placidus宫制</div>
      </div>
      ${angleCard("asc", "上升 ASC", c.asc, "gold-text")}
      ${angleCard("mc", "中天 MC", c.mc, "ziwei-text")}
    </div>`;
  const big = ["太阳", "月亮"].filter(n => planets[n])
    .map(n => `<div class="col-span-2 md:col-span-2">${astroPlanetCard(n, planets[n], true)}</div>`).join("");
  const small = names.filter(n => n !== "太阳" && n !== "月亮")
    .map(n => astroPlanetCard(n, planets[n], false)).join("");
  return `
  <div class="space-y-4">
    ${infoBar}
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">${big}${small}</div>
    <div class="glass p-4"><div class="gold-text mb-2">十二宫宫头</div><div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">${(c.houses || []).map(h=>`<div>第${h.house}宫 · ${esc(h.sign)} ${h.deg}°</div>`).join('')}</div><div class="text-xs text-gray-500 mt-3">本命主要相位 ${(c.aspects || []).length} 组 · 目标日期行运相位 ${((c.transits || {}).aspects_to_natal || []).length} 组</div></div>
    <div class="text-[11px] text-gray-600 px-1">点击行星 / 上升 / 中天查看详情；星座按四象配色（火红 · 土金 · 风紫 · 水蓝）。</div>
  </div>`;
}
/* 星盘详情：复用抽屉组件，数据来自已加载的 astroData，不发额外请求 */
function openAstroDetail(key) {
  const c = astroData || {};
  let name, v, q;
  if (key === "asc" || key === "mc") {
    name = key === "asc" ? "上升 ASC" : "中天 MC";
    v = c[key];
    q = `请解读我的${key === "asc" ? "上升" : "中天"}${(v || {}).sign || ""}`;
  } else {
    name = key.slice(2);
    v = (c.planets || {})[name];
    q = `请解读我的${ASTRO_FULL[name] || name}${(v || {}).sign || ""}`;
  }
  if (!v) return;
  const color = key.startsWith("p:") ? signColor(v.sign) : (key === "asc" ? "#C9A96A" : "#8B7CF6");
  openChartDrawer(`
    ${chartDrawerHead(`${name} · ${v.sign}`, `${v.deg}° · ${SIGN_ELEM[v.sign] ? SIGN_ELEM[v.sign] + "象星座" : ""}`)}
    <div class="glass p-4 text-center mb-4">
      <div class="font-serif text-2xl font-bold" style="color:${color}">${esc(v.sign)}</div>
      <div class="astro-deg astro-deg-big" style="color:${color}">${v.deg}°</div>
    </div>
    <div class="glass p-4 text-sm space-y-2">
      ${infoRow("位置", esc(`${name} ${v.sign} ${v.deg}°`))}
      ${SIGN_ELEM[v.sign] ? infoRow("星座四象", esc(SIGN_ELEM[v.sign] + "象")) : ""}
      ${infoRow("本命宫位", v.house ? `第${v.house}宫` : "角点")}
      ${infoRow("运行状态", v.retrograde ? "逆行" : "顺行")}
      ${infoRow("象征主题", esc(ASTRO_DESC[key.startsWith("p:") ? name : key] || ""))}
    </div>
    ${renderAstroLinks(key)}
    <button class="btn-gold w-full py-2.5 text-sm mt-5" onclick="askLinked('astro',${jsArg(key)},${jsArg(name)})">结合三盘深入解读</button>`);
}

/* ================= ③ 时间轴 ================= */
let tlData = { forecasts: [], stats: {} };
async function loadTimeline() {
  const root = $("#timelineRoot");
  root.innerHTML = `<div class="text-center text-gray-500 text-sm py-16">时间轴加载中…</div>`;
  try { tlData = await apiJson("/api/timeline"); }
  catch (e) {
    if (e.status !== 401) root.innerHTML = errState("时间轴加载失败：" + (e.message || e), "loadTimeline");
    return;
  }
  renderTimeline();
}
function monthWindow() {
  const now = new Date(), arr = [];
  for (let i = -2; i <= 3; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    arr.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return arr;
}
function forecastDims(f) {
  const raw = Array.isArray(f.dimensions) ? f.dimensions : [];
  return raw.map(d => typeof d === "string" ? d : (d && (d.dimension || d.name || d.dim)) || "").filter(Boolean);
}
function cellFlags(f) {
  const txt = ((f.summary || "") + "\n" + (f.full || ""));
  return {
    star: /⭐|机会|大吉|吉/.test(txt),
    warn: /⚠️|⚠|风险|注意|忌|凶/.test(txt)
  };
}
function renderTimeline() {
  const root = $("#timelineRoot");
  const forecasts = tlData.forecasts || [];
  if (!forecasts.length) {
    root.innerHTML = emptyState("时", "尚无预测记录", "对 Agent 说「看看X月运」生成预测后，会出现在这里。");
    return;
  }
  const months = monthWindow();
  const nowM = todayDate().slice(0, 7);
  // 每月一张卡片：单月预测的 target_key 即 YYYY-MM，一个月至多取一条
  const cards = months.map(m => {
    const f = forecasts.find(x => x && x.target_key === m);
    const isNow = m === nowM, isPast = m < nowM;
    const fade = isPast ? "opacity-50" : "";
    const nowBadge = isNow ? `<span class="badge badge-gold">本月</span>` : "";
    if (!f) {
      return `<div class="tl-card tl-empty ${isNow ? "tl-now" : ""} ${fade}">
        <div class="font-serif text-lg whitespace-nowrap ${isNow ? "gold-text font-bold" : "text-gray-400"}">${esc(fmtMonthCn(m))}</div>
        ${isNow ? `<div class="mt-1 self-start">${nowBadge}</div>` : ""}
        <div class="flex-1 flex items-center justify-center text-xs text-gray-600">该月暂无预测</div>
      </div>`;
    }
    const { star, warn } = cellFlags(f);
    const fbCls = f.status === "verified" && f.feedback ? `fb-${f.feedback}` : "";
    const stale = f.status === "stale" ? "stale-stripe" : "";
    const dims = forecastDims(f);
    const flags = `${star ? "⭐" : ""}${warn ? "⚠️" : ""}`;
    return `<div class="tl-card ${fbCls} ${stale} ${isNow ? "tl-now" : ""} ${fade}" title="${esc(f.summary || "")}" onclick="openForecast(${jsArg(f.id)})">
      <div class="flex items-start justify-between gap-2 mb-2">
        <div class="font-serif text-lg leading-tight whitespace-nowrap ${isNow ? "gold-text font-bold" : "text-gray-200"}">${esc(fmtMonthCn(m))}</div>
        <span class="whitespace-nowrap text-sm shrink-0">${flags}${flags && isNow ? " " : ""}${nowBadge}</span>
      </div>
      ${dims.length ? `<div class="mb-2">${dims.map(d => `<span class="badge mr-1 mb-1" style="color:${dimColor(d)};border-color:${dimColor(d)}55;background:${dimColor(d)}14">${esc(d)}</span>`).join("")}</div>` : ""}
      <div class="text-xs text-gray-400 leading-relaxed" style="display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;">${esc(f.summary || "（无摘要）")}</div>
    </div>`;
  }).join("");
  const stats = tlData.stats || {};
  const statBars = DIMS.map(dim => {
    const s = stats[dim.k] || stats[(dim.alias || [])[0]] || {};
    const t = Number(s.total) || 0;
    const rate = t ? Math.round(((Number(s.accurate) || 0) + 0.5 * (Number(s.partial) || 0)) / t * 100) : null;
    return `<div class="flex items-center gap-3">
      <div class="w-16 text-xs shrink-0" style="color:${dim.c}">${dim.k}</div>
      <div class="bar-track flex-1"><div class="bar-fill" style="width:${rate ?? 0}%;background:${dim.c}"></div></div>
      <div class="w-24 text-right text-xs text-gray-400 shrink-0">${rate === null ? "暂无样本" : rate + "%（" + t + " 条）"}</div>
    </div>`;
  }).join("");
  // 长期与专项预测：target_key 非 YYYY-MM 单月的条目（季度/年度/长期等）
  const specials = forecasts.filter(f => f && !/^\d{4}-\d{2}$/.test(String(f.target_key || "")));
  const specialHtml = specials.length ? `
    <div class="mt-5">
      <div class="text-xs tracking-widest text-gray-500 mb-3 px-1">长 期 与 专 项 预 测（${specials.length}）</div>
      <div class="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
        ${specials.map(f => {
          const dims = forecastDims(f);
          const stCls = f.status === "stale" ? "badge-gray" : f.status === "verified" ? "badge-gold" : "badge-purple";
          return `<div class="glass glass-hover p-4 cursor-pointer" onclick="openForecast(${jsArg(f.id)})">
            <div class="flex items-center justify-between gap-2 mb-2">
              <div class="font-serif gold-text">${esc(f.target_key || f.id || "")}</div>
              <span class="badge ${stCls} shrink-0">${esc(f.status || "")}</span>
            </div>
            ${dims.length ? `<div class="mb-2">${dims.map(d => `<span class="badge mr-1 mb-1" style="color:${dimColor(d)};border-color:${dimColor(d)}55;background:${dimColor(d)}14">${esc(d)}</span>`).join("")}</div>` : ""}
            <div class="text-xs text-gray-400 leading-relaxed" style="display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;" title="${esc(f.summary || "")}">${esc(f.summary || "（无摘要）")}</div>
          </div>`;
        }).join("")}
      </div>
    </div>` : "";
  root.innerHTML = `
    <div class="overflow-x-auto pb-1">
      <div class="grid grid-cols-6 gap-3" style="min-width:1040px">${cards}</div>
    </div>
    <div class="flex flex-wrap gap-x-5 gap-y-1 mt-2 px-1 text-[11px] text-gray-500">
      <span>鎏金框 = 本月</span><span>⭐ 机会点</span><span>⚠️ 风险点</span><span>斜纹 = 已过期(stale)</span>
      <span>边框：金=准 · 紫=部分准 · 灰=不准</span><span>点击卡片查看全文并反馈</span>
    </div>
    ${specialHtml}
    <div class="glass p-4 mt-4">
      <div class="text-xs tracking-widest text-gray-500 mb-3">六 维 应 验 率</div>
      <div class="space-y-2.5">${statBars}</div>
      <div class="text-[11px] text-gray-600 mt-3">应验率来自你对每条预测点击「准 / 部分准 / 不准」的反馈累积；尚无反馈的维度显示「暂无样本」。</div>
    </div>`;
}
function openForecast(fid) {
  const f = (tlData.forecasts || []).find(x => x && x.id === fid);
  if (!f) return;
  const dims = forecastDims(f);
  const fb = f.feedback;
  $("#drawer").innerHTML = `
    <div class="flex items-start justify-between mb-4">
      <div>
        <div class="font-serif text-lg gold-text">${esc(f.target_key || "")} 预测</div>
        <div class="text-xs text-gray-500 mt-1">${esc(f.id || "")} · ${esc(f.scope || "")} ·
          <span class="badge ${f.status === "stale" ? "badge-gray" : f.status === "verified" ? "badge-gold" : "badge-purple"}">${esc(f.status || "")}</span></div>
      </div>
      <button class="text-gray-500 hover:text-gray-300 text-xl leading-none px-2" onclick="closeDrawer()">×</button>
    </div>
    ${dims.length ? `<div class="mb-3">${dims.map(d => `<span class="badge mr-1" style="color:${dimColor(d)};border-color:${dimColor(d)}55;background:${dimColor(d)}14">${esc(d)}</span>`).join("")}</div>` : ""}
    ${f.summary ? `<div class="text-sm text-gray-300 mb-3">${esc(f.summary)}</div>` : ""}
    <div class="glass p-4 text-sm msg-body mb-5" style="white-space:pre-wrap">${esc(f.full || "（无全文）")}</div>
    <div class="text-xs tracking-widest text-gray-500 mb-2">应 验 反 馈</div>
    <div class="grid grid-cols-3 gap-2">
      <button class="fb-btn ${fb === "accurate" ? "on-accurate" : ""}" onclick="sendFeedback(${jsArg(fid)},'accurate')">准</button>
      <button class="fb-btn ${fb === "partial" ? "on-partial" : ""}" onclick="sendFeedback(${jsArg(fid)},'partial')">部分准</button>
      <button class="fb-btn ${fb === "off" ? "on-off" : ""}" onclick="sendFeedback(${jsArg(fid)},'off')">不准</button>
    </div>`;
  $("#drawerMask").classList.remove("hidden");
  requestAnimationFrame(() => {$("#drawer").classList.add("open");$("#drawer").querySelector("button")?.focus();});
}
function closeDrawer() {
  const wasOpen=$('#drawer').classList.contains('open');
  $("#drawer").classList.remove("open");
  setTimeout(() => $("#drawerMask").classList.add("hidden"), 200);
  if(wasOpen)restoreFocus('drawer');
}
$("#drawerMask").addEventListener("click", closeDrawer);
async function sendFeedback(fid, fb) {
  try {
    await writeJson('/api/feedback',{forecast_id:fid,feedback:fb});
    const f = (tlData.forecasts || []).find(x => x && x.id === fid);
    if (f) { f.feedback = fb; f.status = "verified"; }
    renderTimeline();
    openForecast(fid);
    toast("已记录反馈");
  } catch (e) {
    if (e.status !== 401) toast("反馈失败：" + (e.message || e));
  }
}

/* ================= ④ 缘网 ================= */
let graphData = null, graphNodes = [], graphLinks = [], graphCanvas = null, graphCtx = null, graphRO = null;
const RELC = { "桃花": "#E8709C", "家人": "#B08D5B", "朋友": "#5FA97A", "同事": "#5B8DD9", "其他": "#8B7CF6" };
async function loadGraph() {
  const root = $("#graphRoot");
  root.innerHTML = `<div class="text-center text-gray-500 text-sm py-16">缘网加载中…</div>`;
  try { graphData = await apiJson("/api/graph"); }
  catch (e) {
    if (e.status !== 401) root.innerHTML = errState("缘网加载失败：" + (e.message || e), "loadGraph");
    return;
  }
  const persons = (graphData && graphData.persons) || [];
  if (!persons.length) {
    root.innerHTML = emptyState("缘", "缘网尚无一节", "对 Agent 说「记下XX，他是我…」即可建立缘网节点。");
    graphData = null;
    if (graphRO) { graphRO.disconnect(); graphRO = null; }
    return;
  }
  root.innerHTML = `
    <div class="flex flex-col lg:flex-row gap-4">
      <div class="glass flex-1 p-2 relative"><canvas id="gcanvas" class="w-full block" style="height:min(66vh,560px)"></canvas></div>
      <aside id="gpanel" class="glass p-4 lg:w-80 shrink-0">
        <div class="text-xs tracking-widest text-gray-500 mb-2">节 点 详 情</div>
        <div class="text-sm text-gray-500">点击左侧节点查看档案与关联事件。</div>
      </aside>
    </div>`;
  graphCanvas = $("#gcanvas");
  graphCtx = graphCanvas.getContext("2d");
  buildGraphLayout();
  const list=document.createElement('div');list.className='graph-person-list';list.setAttribute('aria-label','人物列表');
  list.innerHTML=graphNodes.map((n,i)=>`<button class="quiet-button" data-node="${i}">${esc(n.name)} · ${esc(n.relation)}</button>`).join('');
  list.querySelectorAll('button').forEach(b=>b.onclick=()=>showNodePanel(graphNodes[Number(b.dataset.node)]));root.append(list);
  resizeGraphCanvas();
  canvasClickBind();
  // Tailwind CDN 异步生成 CSS、字体/滚动条到位等都会改变 canvas 的 CSS 尺寸；
  // 位图尺寸必须与最新 CSS 尺寸一致，否则节点视觉位置与点击命中坐标错位（位图被缩放）
  if (graphRO) graphRO.disconnect();
  if (window.ResizeObserver) {
    graphRO = new ResizeObserver(() => resizeGraphCanvas());
    graphRO.observe(graphCanvas);
  }
}
function buildGraphLayout() {
  const persons = graphData.persons || [];
  const rels = graphData.relations || [];
  graphNodes = [{ id: "me", name: "我", relation: "我", fx: true }];
  persons.forEach(p => graphNodes.push({ id: p.id || p.name, name: p.name || "?", relation: p.relation || "其他", raw: p }));
  graphLinks = rels.map(r => ({ from: r.from, to: r.to, type: r.type || "", trend: r.trend || "" }))
                   .filter(l => l.from && l.to);
}
function resizeGraphCanvas(retried) {
  if (!graphCanvas || !graphCanvas.isConnected) return;
  const dpr = window.devicePixelRatio || 1;
  const w = graphCanvas.clientWidth, h = graphCanvas.clientHeight;
  if (!w || !h) {
    // 容器尚未有尺寸（如页签刚切换/未显示），下一帧重试一次
    if (!retried) requestAnimationFrame(() => resizeGraphCanvas(true));
    return;
  }
  graphCanvas.width = w * dpr; graphCanvas.height = h * dpr;
  graphCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  layoutForce(w, h);
  drawGraph(w, h, 1);
}
function layoutForce(w, h) {
  const cx = w / 2, cy = h / 2;
  const ring = Math.max(90, Math.min(w, h) * 0.36);
  const ns = graphNodes;
  ns[0].x = cx; ns[0].y = cy;
  const others = ns.slice(1);
  others.forEach((n, i) => {
    const a = (i / Math.max(others.length, 1)) * Math.PI * 2 - Math.PI / 2;
    n.x = cx + Math.cos(a) * ring;
    n.y = cy + Math.sin(a) * ring;
    n.tx = n.x; n.ty = n.y;
  });
  // 简易力导向：节点间斥力 + 环向弹簧，迭代收敛
  for (let it = 0; it < 160; it++) {
    for (let i = 1; i < ns.length; i++) {
      const n = ns[i];
      let fx = (n.tx - n.x) * 0.02, fy = (n.ty - n.y) * 0.02;
      for (let j = 0; j < ns.length; j++) {
        if (i === j) continue;
        const m = ns[j];
        let dx = n.x - m.x, dy = n.y - m.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) { dx = Math.random() - .5; dy = Math.random() - .5; d2 = 1; }
        const d = Math.sqrt(d2);
        const rep = Math.min(1600 / d2, 8);
        fx += dx / d * rep; fy += dy / d * rep;
      }
      // 限制单迭代步长，避免少数节点时位置被斥力推飞
      const step = Math.hypot(fx, fy);
      if (step > 6) { fx = fx / step * 6; fy = fy / step * 6; }
      n.x += fx; n.y += fy;
    }
  }
  // 收敛后钳制在画布范围内（留出边距），保证节点与名字标签不跑出可视区
  const mgn = 44;
  for (let i = 1; i < ns.length; i++) {
    ns[i].x = Math.max(mgn, Math.min(w - mgn, ns[i].x));
    ns[i].y = Math.max(mgn, Math.min(h - mgn, ns[i].y));
  }
}
function drawGraph(w, h, alpha) {
  const ctx = graphCtx;
  ctx.clearRect(0, 0, w, h);
  ctx.globalAlpha = alpha;
  const pos = {}; graphNodes.forEach(n => pos[n.id] = n);
  // 连线
  graphLinks.forEach(l => {
    const a = pos[l.from], b = pos[l.to];
    if (!a || !b) return;
    ctx.strokeStyle = "rgba(201,169,106,.28)";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    if (l.type) {
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      ctx.fillStyle = "#69735f";
      ctx.font = "10px 'Noto Sans SC'";
      ctx.textAlign = "center";
      ctx.fillText(l.type + (l.trend ? "·" + l.trend : ""), mx, my - 4);
    }
  });
  // 节点
  graphNodes.forEach(n => {
    const isMe = n.id === "me";
    const col = isMe ? "#C9A96A" : (RELC[n.relation] || RELC["其他"]);
    const r = isMe ? 26 : 19;
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
    ctx.fillStyle = isMe ? "rgba(201,169,106,.18)" : "#f0f2e8";
    ctx.fill();
    ctx.strokeStyle = col; ctx.lineWidth = isMe ? 2 : 1.4; ctx.stroke();
    ctx.fillStyle = col;
    ctx.font = (isMe ? "bold 13px" : "12px") + " 'Noto Serif SC'";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(isMe ? "我" : (n.name || "?").slice(0, 3), n.x, n.y);
    if (!isMe) {
      ctx.fillStyle = "#6e795f";
      ctx.font = "11px 'Noto Sans SC'";
      ctx.fillText(n.name || "?", n.x, n.y + 32);
    }
  });
  ctx.globalAlpha = 1;
}
function canvasClickBind() {
  let lastTouch = 0;
  const hit = pt => {
    if (!graphCanvas || !graphCanvas.isConnected) return;
    const rect = graphCanvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    // 布局坐标基于 CSS 像素(clientWidth/clientHeight)；按 rect 实际比例换算，
    // 兼容 devicePixelRatio、浏览器缩放及 canvas 被 CSS 拉伸的情况
    const sx = graphCanvas.clientWidth / rect.width;
    const sy = graphCanvas.clientHeight / rect.height;
    const x = (pt.clientX - rect.left) * sx;
    const y = (pt.clientY - rect.top) * sy;
    let best = null, bd = 1e9;
    graphNodes.forEach(n => {
      if (n.x == null || n.y == null) return;
      const d = Math.hypot(n.x - x, n.y - y);
      const hr = n.id === "me" ? 32 : 34; // 命中半径略大于绘制半径，照顾触屏
      if (d <= hr && d < bd) { bd = d; best = n; }
    });
    if (best) showNodePanel(best); else resetNodePanel();
  };
  graphCanvas.addEventListener("click", e => {
    if (Date.now() - lastTouch < 500) return; // 触屏 touchend 已处理，避免重复触发
    hit(e);
  });
  graphCanvas.addEventListener("touchend", e => {
    if (!e.changedTouches || !e.changedTouches.length) return;
    lastTouch = Date.now();
    hit(e.changedTouches[0]);
  }, { passive: true });
}
function resetNodePanel() {
  const panel = $("#gpanel");
  if (!panel) return;
  panel.innerHTML = `
    <div class="text-xs tracking-widest text-gray-500 mb-2">节 点 详 情</div>
    <div class="text-sm text-gray-500">点击左侧节点查看档案与关联事件；点击空白处收起。</div>`;
}
window.addEventListener("resize", () => { if (currentPage === "graph") resizeGraphCanvas(); });
function showNodePanel(n) {
  const panel = $("#gpanel");
  if (n.id === "me") {
    const evs = ((graphData && graphData.events) || []).filter(e => (e.actors || []).includes("me"));
    panel.innerHTML = `
      <div class="font-serif text-lg gold-text mb-1">我</div>
      <div class="text-xs text-gray-500 mb-4">缘网中心节点</div>
      <div class="text-xs tracking-widest text-gray-500 mb-2">关 联 事 件（${evs.length}）</div>
      ${eventsTimeline(evs)}`;
    return;
  }
  const p = n.raw || {};
  const rels = (graphData.relations || []).filter(r => r.from === n.id || r.to === n.id);
  const evs = ((graphData && graphData.events) || []).filter(e => (e.actors || []).includes(n.id));
  const birth = (p.birth && p.birth.solar_datetime)
    ? esc(p.birth.solar_datetime) + (p.birth.time_unknown ? "（时辰未知）" : "")
    : "未登记";
  const cht = p.chart || {};
  const chartHtml = cht.pillars ? `
    <div class="text-xs tracking-widest text-gray-500 mb-2">命 盘${(p.birth && p.birth.time_unknown) ? `<span class="text-gray-600">（时辰未知；历史盘面仅供回看，需核对出生资料）</span>` : ""}</div>
    <div class="glass p-3 mb-3">
      <div class="grid grid-cols-4 gap-1 text-center">
        ${[["year", "年"], ["month", "月"], ["day", "日"], ["hour", "时"]].map(([k, zh]) => {
          const pl = cht.pillars[k] || {};
          const gan = pl.gan || (pl.ganzhi || "")[0] || "—";
          const zhi = pl.zhi || (pl.ganzhi || "")[1] || "—";
          return `<div><div class="text-[10px] text-gray-500">${zh}</div>
            <div class="font-serif" style="color:${wxColor(pl.wuxing_gan)}">${esc(gan)}</div>
            <div class="font-serif" style="color:${wxColor(pl.wuxing_zhi)}">${esc(zhi)}</div></div>`;
        }).join("")}
      </div>
      <div class="text-xs text-gray-400 mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        ${cht.day_master ? `<span>日主 <span class="font-serif" style="color:${wxColor(cht.day_master_wuxing)}">${esc(cht.day_master)}</span></span>` : ""}
        ${(cht.xiyongshen || []).length ? `<span>生扶与克泄提示（启发式，未完整论证） ${cht.xiyongshen.map(x => `<span style="color:${wxColor(x)}">${esc(x)}</span>`).join(" ")}</span>` : ""}
      </div>
    </div>` : "";
  panel.innerHTML = `
    <div class="flex items-center gap-2 mb-1">
      <div class="font-serif text-lg" style="color:${RELC[n.relation] || RELC["其他"]}">${esc(p.name || "?")}</div>
      <span class="badge" style="color:${RELC[n.relation] || RELC["其他"]};border-color:${(RELC[n.relation] || RELC["其他"])}55;background:${(RELC[n.relation] || RELC["其他"])}14">${esc(n.relation)}</span>
    </div>
    <div class="text-xs text-gray-500 space-y-1 mb-3">
      <div>出生：${birth}</div>
      ${p.created_at ? `<div>建档：${esc(p.created_at)}</div>` : ""}
    </div>
    ${chartHtml}
    ${(p.tags || []).length ? `<div class="mb-3">${p.tags.map(t => `<span class="badge badge-purple mr-1">${esc(t)}</span>`).join("")}</div>` : ""}
    ${p.notes ? `<div class="glass p-3 text-xs text-gray-300 mb-3" style="white-space:pre-wrap">${esc(p.notes)}</div>` : ""}
    ${rels.length ? `<div class="text-xs tracking-widest text-gray-500 mb-2">关 系</div>
      <div class="space-y-1 mb-4">${rels.map(r => `<div class="text-xs text-gray-400">${esc(r.from)} → ${esc(r.to)}：<span class="text-gray-200">${esc(r.type || "")}</span>${r.trend ? ` <span class="text-gray-500">(${esc(r.trend)})</span>` : ""}</div>`).join("")}</div>` : ""}
    <div class="text-xs tracking-widest text-gray-500 mb-2">关 联 事 件（${evs.length}）</div>
    ${eventsTimeline(evs)}`;
}
function eventsTimeline(evs) {
  if (!evs.length) return `<div class="text-xs text-gray-600">暂无关联事件。</div>`;
  const sorted = evs.slice().sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
  return `<div class="space-y-2 relative pl-3" style="border-left:1px solid rgba(201,169,106,.25)">
    ${sorted.map(e => `
      <div class="glass p-2.5 text-xs">
        <div class="flex items-center gap-2 mb-1">
          <span class="text-gray-500">${esc(e.date || "")}</span>
          <span class="badge" style="color:${dimColor(e.type)};border-color:${dimColor(e.type)}55;background:${dimColor(e.type)}14">${esc(e.type || "其他")}</span>
          ${e.verified ? `<span class="gold-text" title="已验证">✓</span>` : ""}
        </div>
        ${e.omen ? `<div class="text-gray-300">断语：${esc(e.omen)}</div>` : ""}
        ${e.notes ? `<div class="text-gray-500 mt-0.5">${esc(e.notes)}</div>` : ""}
      </div>`).join("")}
  </div>`;
}

/* ================= ⑤ 词典 ================= */
async function loadDict() {
  const root = $("#dictRoot");
  root.innerHTML = `<div class="text-center text-gray-500 text-sm py-16">词典加载中…</div>`;
  let dict, stats;
  try {
    [dict, stats] = await Promise.all([
      apiJson("/api/archive?section=omen_dictionary"),
      apiJson("/api/archive?section=dimension_stats")
    ]);
  } catch (e) {
    if (e.status !== 401) root.innerHTML = errState("词典加载失败：" + (e.message || e), "loadDict");
    return;
  }
  dict = Array.isArray(dict) ? dict : [];
  stats = stats || {};
  if (!dict.length) {
    root.innerHTML = emptyState("典", "词典尚无条目", "对话中验证过的断语会自动登记进词典。");
    return;
  }
  const total = dict.length;
  const highN = dict.filter(d => d.confidence === "高").length;
  const highPct = total ? Math.round(highN / total * 100) : 0;
  const rank = DIMS.map(dim => {
    const s = stats[dim.k] || stats[(dim.alias || [])[0]] || {};
    const t = Number(s.total) || 0;
    const rate = t ? Math.round(((Number(s.accurate) || 0) + 0.5 * (Number(s.partial) || 0)) / t * 100) : -1;
    return { dim, t, rate };
  }).sort((a, b) => b.rate - a.rate);
  const rankHtml = rank.map(r =>
    `<div class="flex items-center gap-2">
      <span class="text-xs w-14 shrink-0" style="color:${r.dim.c}">${r.dim.k}</span>
      <div class="bar-track flex-1"><div class="bar-fill" style="width:${Math.max(r.rate, 0)}%;background:${r.dim.c}"></div></div>
      <span class="text-xs text-gray-400 w-16 text-right shrink-0">${r.rate < 0 ? "暂无样本" : r.rate + "%"}</span>
    </div>`).join("");
  const badgeOf = c => c === "高" ? "badge-gold" : c === "中" ? "badge-purple" : "badge-gray";
  const rows = dict.map(d => `
    <tr class="border-b border-white/5 hover:bg-white/[.02]">
      <td class="px-3 py-2.5 font-serif text-gray-100">${esc(d.omen || "")}</td>
      <td class="px-3 py-2.5 text-gray-400">${esc(d.generic || "")}</td>
      <td class="px-3 py-2.5 gold-text font-medium">${esc(d.personal || "—")}</td>
      <td class="px-3 py-2.5"><span class="badge" style="color:${dimColor(d.dimension)};border-color:${dimColor(d.dimension)}55;background:${dimColor(d.dimension)}14">${esc(d.dimension || "")}</span></td>
      <td class="px-3 py-2.5 text-center text-gray-300">${d.samples ?? 0}</td>
      <td class="px-3 py-2.5 text-center"><span class="badge ${badgeOf(d.confidence)}">${esc(d.confidence || "低")}</span></td>
      <td class="px-3 py-2.5 text-center text-gray-500">v${d.version ?? 1}</td>
    </tr>`).join("");
  root.innerHTML = `
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
      <div class="glass p-4 text-center">
        <div class="text-2xl font-serif font-bold gold-text">${total}</div>
        <div class="text-xs text-gray-500 mt-1">词典条数</div>
      </div>
      <div class="glass p-4 text-center">
        <div class="text-2xl font-serif font-bold ziwei-text">${highPct}%</div>
        <div class="text-xs text-gray-500 mt-1">高置信占比（${highN}/${total}）</div>
      </div>
      <div class="glass p-4">
        <div class="text-xs text-gray-500 mb-2">六维准确率排行</div>
        <div class="space-y-1.5">${rankHtml}</div>
      </div>
    </div>
    <div class="glass overflow-x-auto">
      <table class="w-full text-sm" style="min-width:760px">
        <thead><tr class="text-xs text-gray-500 border-b border-white/10">
          <th class="px-3 py-2.5 text-left font-normal">断语</th>
          <th class="px-3 py-2.5 text-left font-normal">通用义</th>
          <th class="px-3 py-2.5 text-left font-normal">你的个人义</th>
          <th class="px-3 py-2.5 text-left font-normal">维度</th>
          <th class="px-3 py-2.5 font-normal">样本数</th>
          <th class="px-3 py-2.5 font-normal">置信度</th>
          <th class="px-3 py-2.5 font-normal">version</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

/* ================= ⑥ 报告（飞书推送回看，archive.reports） ================= */
const REPORT_TYPE_C = { "晨报": "#C9A96A", "周报": "#8B7CF6", "月报": "#5B8DD9", "季报": "#5FA97A" };
const CHANNEL_NAME = { feishu: "飞书", web: "网页" };

/* 时间表与下一期时刻由服务器计算；浏览器只提交用户实际修改的配置。 */
const REPORT_KINDS = {daily:'晨报',weekly:'周报',monthly:'月报',quarterly:'季报'};
const REPORT_WEEKDAYS = ['星期一','星期二','星期三','星期四','星期五','星期六','星期日'];
const reportSettingsState = {snapshots:new Map(),drafts:new Map(),conflicts:new Set(),busy:new Set(),loadVersion:0};
function reportSettingsPayload(value) {
  const rows=value?.schedules;
  if(value?.timezone!=='Asia/Shanghai' || value.prepare_minutes!==15 || !Array.isArray(rows) || rows.length!==4
      || new Set(rows.map(r=>r.kind)).size!==4 || rows.some(r=>!Object.hasOwn(REPORT_KINDS,r.kind) || !Number.isInteger(r.revision)))
    throw Error('报告时间表暂时不完整，请重新读取。');
  return rows;
}
function reportScheduleDraft(row) {
  const draft={enabled:!!row.enabled,time:String(row.time || '')};
  if(row.kind==='weekly')draft.weekday=row.weekday;
  if(row.kind==='monthly' || row.kind==='quarterly')draft.day=row.day;
  return draft;
}
function reportSettingDate(value) {
  if(!value || !Number.isFinite(new Date(value).getTime()))return '暂无下一期';
  return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));
}
function reportSchedulePreview(row) {
  const active=row.status==='active' && row.enabled;
  const preparation=active?row.next_prepare:row.preview_prepare,delivery=active?row.next_delivery:row.preview_delivery;
  return `<p class="schedule-preview-title">${active?'下一期安排':'启用后的时间预览'}</p><dl class="schedule-preview"><div><dt>提前准备</dt><dd>${esc(reportSettingDate(preparation))}</dd></div><div><dt>报告发送</dt><dd>${esc(reportSettingDate(delivery))}</dd></div></dl>`;
}
function reportScheduleCard(row) {
  const kind=row.kind,draft=reportSettingsState.drafts.get(kind) || reportScheduleDraft(row),prefix='report-'+kind;
  const status=Number(row.delivery_state?.sending)>0?'发送中':Number(row.delivery_state?.uncertain)>0?'送达待核对':({active:'已启用',paused:'已暂停',unconfigured:'渠道尚未配置',uninitialized:'尚未保存设置'})[row.status] || '等待核对';
  const weekday=kind==='weekly'?`<label for="${prefix}-weekday">每周发送日</label><select id="${prefix}-weekday" name="weekday">${REPORT_WEEKDAYS.map((label,i)=>`<option value="${i+1}" ${Number(draft.weekday)===i+1?'selected':''}>${label}</option>`).join('')}</select>`:'';
  const day=['monthly','quarterly'].includes(kind)?`<label for="${prefix}-day">${kind==='quarterly'?'季首月发送日':'每月发送日'}</label><select id="${prefix}-day" name="day">${Array.from({length:28},(_,i)=>`<option value="${i+1}" ${Number(draft.day)===i+1?'selected':''}>${i+1} 日</option>`).join('')}<option value="last" ${draft.day==='last'?'selected':''}>月末（最后一天）</option></select>`:'';
  return `<article class="schedule-card" data-report-kind="${kind}"><form id="${prefix}-form" aria-labelledby="${prefix}-title"><div class="schedule-heading"><h2 id="${prefix}-title">${REPORT_KINDS[kind]}</h2><span class="schedule-state">${esc(status)}</span></div><label class="schedule-enabled" for="${prefix}-enabled"><input type="checkbox" id="${prefix}-enabled" name="enabled" ${draft.enabled?'checked':''}>启用${REPORT_KINDS[kind]}</label><div class="schedule-fields"><label for="${prefix}-time">发送时间（北京时间）</label><input id="${prefix}-time" name="time" type="time" step="60" required value="${esc(draft.time)}">${weekday}${day}</div>${kind==='daily'?'<p class="muted">每天发送一期。</p>':kind==='quarterly'?'<p class="muted">仅在 1、4、7、10 月发送；月末指这些月份的最后一天。</p>':''}${reportSchedulePreview(row)}<p class="schedule-preview-note muted">预览来自当前已保存设置；修改后保存即可更新。</p>${row.status_reason?`<p class="schedule-reason">${esc(row.status_reason)}</p>`:''}<div class="schedule-actions"><button type="submit" class="btn-gold schedule-save">保存${REPORT_KINDS[kind]}设置</button><button type="button" class="quiet-button schedule-refresh ${reportSettingsState.conflicts.has(kind)?'':'hidden'}">读取最新设置</button></div><p class="schedule-feedback" role="status" aria-live="polite"></p></form></article>`;
}
function readReportScheduleDraft(form,kind) {
  const draft={enabled:form.elements.enabled.checked,time:form.elements.time.value};
  if(kind==='weekly')draft.weekday=Number(form.elements.weekday.value);
  if(kind==='monthly' || kind==='quarterly')draft.day=form.elements.day.value==='last'?'last':Number(form.elements.day.value);
  return draft;
}
function reportScheduleMessage(form,text,error=false) {
  const status=form.querySelector('.schedule-feedback');status.textContent=text;status.classList.toggle('err-banner',error);
}
function reportScheduleControls(kind) {
  const row=reportSettingsState.snapshots.get(kind),form=$('#report-'+kind+'-form');if(!row || !form)return;
  const busy=reportSettingsState.busy.has(kind),editable=row.configured===true && row.can_modify===true;
  form.setAttribute('aria-busy',String(busy));
  form.querySelectorAll('input,select').forEach(control=>control.disabled=busy || !editable);
  form.querySelector('.schedule-save').disabled=busy || !editable || reportSettingsState.conflicts.has(kind);
  form.querySelector('.schedule-refresh').disabled=busy;
}
function bindReportScheduleForm(kind) {
  const form=$('#report-'+kind+'-form');
  const changed=()=>{reportSettingsState.drafts.set(kind,readReportScheduleDraft(form,kind));if(!reportSettingsState.conflicts.has(kind))reportScheduleMessage(form,'有未保存的修改，时间预览仍以已保存设置为准。');};
  form.oninput=changed;form.onchange=changed;
  form.onsubmit=event=>{event.preventDefault();saveReportSchedule(kind);};
  form.querySelector('.schedule-refresh').onclick=()=>refreshReportSchedule(kind);
  reportScheduleControls(kind);
  if(reportSettingsState.conflicts.has(kind))reportScheduleMessage(form,'设置在填写期间有更新，草稿仍保留。请读取最新设置并核对后保存。',true);
}
function replaceReportScheduleCard(kind,focusSelector) {
  const previous=$(`[data-report-kind="${kind}"]`);if(!previous)return;
  previous.outerHTML=reportScheduleCard(reportSettingsState.snapshots.get(kind));bindReportScheduleForm(kind);
  if(focusSelector)$('#report-'+kind+'-form').querySelector(focusSelector)?.focus({preventScroll:true});
}
async function loadReportSettings() {
  if(reportSettingsState.busy.size){toast('正在保存设置，请等服务器回执后再刷新。');return;}
  const root=$('#reportSettingsRoot'),version=++reportSettingsState.loadVersion;root.setAttribute('aria-busy','true');
  if(!root.querySelector('.schedule-card'))root.innerHTML='<p class="muted">正在读取报告时间表…</p>';
  try {
    const response=await apiJson('/api/reports/schedules'),rows=reportSettingsPayload(response);if(version!==reportSettingsState.loadVersion)return;
    rows.forEach(row=>reportSettingsState.snapshots.set(row.kind,row));
    root.innerHTML='<div class="schedule-intro"><p>所有时间均为<strong>北京时间（Asia/Shanghai）</strong>。报告会提前 <strong>15 分钟</strong>准备。</p><p class="muted">发送渠道由已绑定的账户决定。这里仅调整时间与启用状态；正在发送的报告需要等待当前投递结束。</p><div class="schedule-intro-actions"><a href="#/reports">返回报告存档</a><button type="button" class="quiet-button" id="refreshReportSettingsBtn">刷新时间表</button></div></div><div class="schedule-grid">'+Object.keys(REPORT_KINDS).map(kind=>reportScheduleCard(reportSettingsState.snapshots.get(kind))).join('')+'</div>';
    $('#refreshReportSettingsBtn').onclick=async()=>{await loadReportSettings();$('#refreshReportSettingsBtn')?.focus({preventScroll:true});};
    Object.keys(REPORT_KINDS).forEach(bindReportScheduleForm);
  }catch(e){if(version===reportSettingsState.loadVersion && !root.querySelector('.schedule-card'))root.innerHTML=errState('报告设置读取失败：'+e.message,'loadReportSettings');else if(version===reportSettingsState.loadVersion)toast('报告设置读取失败，草稿仍保留：'+e.message);}
  finally{if(version===reportSettingsState.loadVersion)root.setAttribute('aria-busy','false');}
}
async function saveReportSchedule(kind) {
  const row=reportSettingsState.snapshots.get(kind),form=$('#report-'+kind+'-form');
  if(!row || reportSettingsState.busy.has(kind) || reportSettingsState.conflicts.has(kind) || !row.configured || !row.can_modify || !form.reportValidity())return;
  const draft=readReportScheduleDraft(form,kind),body={kind,expected_revision:row.revision,...draft},operation='report-schedule:'+kind;
  reportSettingsState.drafts.set(kind,draft);body.request_id=tarotOperationKey(operation,body);
  reportSettingsState.busy.add(kind);reportScheduleControls(kind);reportScheduleMessage(form,'正在保存，等待服务器回执…');
  try {
    const result=await apiJson('/api/reports/schedules',{method:'PATCH',body:JSON.stringify(body)});
    if(result.kind!==kind || result.receipt?.id!==kind || result.receipt?.kind!=='report_schedule' || result.receipt.write_status!=='saved' || !Number.isInteger(result.revision) || result.receipt.revision!==result.revision)
      throw Error('尚未收到完整保存回执，请重试核对。');
    reportSettingsState.snapshots.set(kind,result);reportSettingsState.drafts.delete(kind);clearTarotOperation(operation);
    replaceReportScheduleCard(kind);reportScheduleMessage($('#report-'+kind+'-form'),`已保存${REPORT_KINDS[kind]}设置，版本 ${result.receipt.revision}。`);
    loaded.reports=false;
  }catch(e){
    if(e.status===409){reportSettingsState.conflicts.add(kind);form.querySelector('.schedule-refresh').classList.remove('hidden');reportScheduleMessage(form,'设置在填写期间有更新，草稿仍保留。请读取最新设置并核对后保存。',true);}
    else reportScheduleMessage(form,'尚未确认保存，草稿仍保留：'+e.message,true);
  }finally{reportSettingsState.busy.delete(kind);reportScheduleControls(kind);$('#report-'+kind+'-form '+(reportSettingsState.conflicts.has(kind)?'.schedule-refresh':'.schedule-save'))?.focus({preventScroll:true});}
}
async function refreshReportSchedule(kind) {
  if(reportSettingsState.busy.has(kind))return;
  const form=$('#report-'+kind+'-form');reportSettingsState.drafts.set(kind,readReportScheduleDraft(form,kind));
  reportSettingsState.busy.add(kind);reportScheduleControls(kind);reportScheduleMessage(form,'正在读取最新设置，草稿仍保留…');
  try{
    const response=await apiJson('/api/reports/schedules'),row=reportSettingsPayload(response).find(item=>item.kind===kind);
    reportSettingsState.snapshots.set(kind,row);reportSettingsState.conflicts.delete(kind);replaceReportScheduleCard(kind);
    reportScheduleMessage($('#report-'+kind+'-form'),'已读取最新设置；你的草稿仍保留，请核对后重新保存。');
  }catch(e){reportScheduleMessage(form,'最新设置读取失败，草稿仍保留：'+e.message,true);}
  finally{reportSettingsState.busy.delete(kind);reportScheduleControls(kind);$('#report-'+kind+'-form '+(reportSettingsState.conflicts.has(kind)?'.schedule-refresh':'.schedule-save'))?.focus({preventScroll:true});}
}
$('#openReportSettingsBtn').onclick=()=>{switchPage('reportsettings');$('#pageTitle').tabIndex=-1;$('#pageTitle').focus({preventScroll:true});};

function reportCardHtml(r) {
  const c = REPORT_TYPE_C[r.type] || "#9AA1B5";
  const vc = Number(r.verified_count) || 0;
  const ch = CHANNEL_NAME[r.channel] || r.channel || "";
  return `<div class="report-card" data-date="${esc(r.date || "")}">
    <div class="report-head flex items-center gap-2 flex-wrap px-4 py-3">
      <span class="badge" style="color:${c};border-color:${c}55;background:${c}14">${esc(r.type || "报告")}</span>
      <span class="font-serif text-gray-100">${esc(r.date || "")}</span>
      ${ch ? `<span class="text-xs text-gray-500">${esc(ch)}</span>` : ""}
      ${r.recovered_from ? `<span class="text-xs text-gray-500">历史补归档 · 保留原文</span>` : ""}
      ${vc ? `<span class="text-xs gold-text">已验证${vc}条</span>` : ""}
      <span class="flex-1"></span>
      <span class="report-toggle text-xs text-gray-500">收起 ▲</span>
    </div>
    <div class="report-body msg-body px-4 pb-4 pt-3" style="border-top:1px solid rgba(255,255,255,.06)">${r.guidance?answerHtml(r.guidance,r.content):md(r.content || "")}</div>
  </div>`;
}
function toggleReportCard(card) {
  const body = card.querySelector(".report-body");
  const hide = !body.classList.contains("hidden");
  body.classList.toggle("hidden", hide);
  card.querySelector(".report-toggle").textContent = hide ? "展开 ▼" : "收起 ▲";
}
function locateReport(date) {
  const root = $("#reportsRoot");
  root.querySelectorAll(".report-card.hl").forEach(c => c.classList.remove("hl"));
  if (!date) return;
  const card = root.querySelector(`.report-card[data-date="${CSS.escape(date)}"]`);
  if (!card) { toast(`未找到 ${date} 的报告`); return; }
  card.classList.add("hl");
  if (card.querySelector(".report-body").classList.contains("hidden")) toggleReportCard(card);
  setTimeout(() => card.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
}
async function loadReports() {
  const root = $("#reportsRoot");
  root.innerHTML = `<div class="text-center text-gray-500 text-sm py-16">报告加载中…</div>`;
  if (!getToken()) { openTokenModal(false); return; }  // 深读链接首次访问：先收口令，进入后自动重载
  let list;
  try { list = await apiJson('/api/reports'); }
  catch (e) {
    if (e.status !== 401) root.innerHTML = errState("报告加载失败：" + (e.message || e), "loadReports");
    return;
  }
  list = Array.isArray(list) ? list.slice() : [];
  list.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
  if (!list.length) {
    root.innerHTML = emptyState("报", "暂无报告", "飞书推送的报告会自动归档到这里。")+'<div id="reportQueue"></div>'; loadReportQueue();
    return;
  }
  root.innerHTML = `<div class="report-summary"><div>阅读存档<strong>${list.length} 篇</strong></div><div>最新一期<strong>${esc(list[0].date)}</strong></div><div>发送安排<strong>见报告设置</strong></div></div><details class="report-delivery"><summary>查看生成与投递状态</summary><div id="reportQueue">正在读取…</div></details><div class="reports-toolbar"><input id="reportQuery" placeholder="搜索报告正文或日期" aria-label="搜索报告"><select id="reportKind" aria-label="报告类型"><option value="">全部报告</option>${Object.keys(REPORT_TYPE_C).map(k=>`<option>${k}</option>`).join('')}</select><button id="exportReports" class="quiet-button">导出所选报告</button><button id="printReports" class="quiet-button">打印</button></div><div id="reportList" class="max-w-4xl mx-auto space-y-4"></div>`;
  let filtered=list;
  function renderFiltered() {
    const q=$('#reportQuery').value.toLowerCase(),kind=$('#reportKind').value;
    filtered=list.filter(r=>(!kind || r.type===kind) && (!q || (r.date+' '+r.content).toLowerCase().includes(q)));
    $('#reportList').innerHTML=filtered.length?filtered.map(reportCardHtml).join(''):emptyState('报','没有匹配的报告','试试其他日期或关键词');
    $('#reportList').querySelectorAll('.report-head').forEach(h=>{h.setAttribute('role','button');h.tabIndex=0;h.onclick=()=>toggleReportCard(h.closest('.report-card'));h.onkeydown=e=>{if(e.key==='Enter' || e.key===' '){e.preventDefault();h.click();}};});
  }
  $('#reportQuery').oninput=renderFiltered;$('#reportKind').onchange=renderFiltered;renderFiltered();
  $('#exportReports').onclick=()=>downloadText('明镜台-报告.md',filtered.map(r=>'# '+r.date+' '+r.type+'\n\n'+r.content).join('\n\n---\n\n'));
  $('#printReports').onclick=()=>window.print();
  loadReportQueue();

  if (pendingReportDate) { const d = pendingReportDate; pendingReportDate = ""; locateReport(d); }
}

function downloadText(name,content) {const u=URL.createObjectURL(new Blob([content],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
async function loadReportQueue() {
 const root=$('#reportQueue');if(!root)return;
 try{const status=await apiJson('/api/reports/status'),rows=status.outbox?.rows || status.rows || [];
   const labels={pending:'已归档，待发送',ready:'已归档，待发送',sending:'投递中',sent:'已送达',rejected:'渠道明确拒绝，等待有限重试',stale:'依据已改变，等待重新准备',cancelled:'授权或来源已撤回',uncertain:'送达待核对',expired:'已过时段'};
   root.innerHTML='<p class="muted">按 Asia/Shanghai 时区定时准备与投递；送达待核对时，需先核对实际回执。</p>'+rows.slice(0,16).map(r=>`<div class="queue-row"><span>${esc(r.date || r.due?.slice(0,10) || '')} ${esc(({daily:'晨报',weekly:'周报',monthly:'月报',quarterly:'季报'})[r.kind] || '报告')}</span><span>${esc(labels[r.status] || r.status)}</span>${r.error?`<small>${esc(r.error)}</small>`:''}</div>`).join('');
 }catch(e){root.innerHTML=`<p class="muted">投递状态暂不可用：${esc(e.message)}</p>`;}
}

/* ================= 塔罗：牌由服务端抽取，解释重试始终使用同一个 draw ================= */
const tarotState={deck:null,draws:[],cases:[],draw:null,readings:[],busy:false,reading:false,loadVersion:0,nextExplicit:false,previousDraw:null,nextCaseId:undefined,skipMotion:false,animatePositions:[]};
function tarotList(value) {return Array.isArray(value)?value:[];}
function tarotCard(id) {return tarotList(tarotState.deck?.cards).find(c=>c.card_id===id) || {};}
function tarotSpread() {return tarotList(tarotState.deck?.spreads).find(s=>s.id===$('#tarotSpread').value) || {id:'reflect3',positions:['当前处境的反思','可能忽视的因素','可尝试的行动']};}
function tarotPositions(spread) {return tarotList(spread?.positions).map((p,i)=>typeof p==='string'?{label:p,position:i}:{...p,label:p.label || p.name || p.meaning || `第 ${i+1} 张`,position:p.position ?? i});}
function tarotStatus(text,error=false) {const el=$('#tarotStatus');el.textContent=text;el.classList.toggle('hidden',!text);el.classList.toggle('err-banner',error);}
function tarotOperationKey(operation, body) {
  const key='tarot-request:'+operation, previous=operationCache.get(key) || storedJson(key,null), fingerprint=JSON.stringify(body);
  if(previous?.fingerprint===fingerprint)return previous.id;
  const id=crypto.randomUUID(),value={id,fingerprint};operationCache.set(key,value);try{sessionStorage.setItem(key,JSON.stringify(value));}catch{}return id;
}
function clearTarotOperation(operation) {const key='tarot-request:'+operation;operationCache.delete(key);sessionStorage.removeItem(key);}
function tarotSafeImage(cardId) {return /^[a-zA-Z0-9_-]+$/.test(String(cardId || ''))?'/static/tarot/'+cardId+'.svg':'/static/tarot/back.svg';}
function tarotOrientation(value) {return value==='reversed'?'逆位':'正位';}
function tarotText(value) {return Array.isArray(value)?value.filter(v=>typeof v==='string').join('；'):typeof value==='string'?value:'';}
function tarotBackground(draw) {return tarotText(draw?.background ?? draw?.context_snapshot?.background);}
function caseBackground(entry) {
  if(!entry)return '';
  const goal=entry.goal ?? entry.state?.goal ?? '',conditions=tarotText(entry.state?.conditions || entry.conditions);
  return [goal?String(goal):'',conditions?'已知条件：'+conditions:''].filter(Boolean).join('\n');
}
function tarotPositionName(card,index) {return card.label || tarotPositions(tarotState.draw?.spread)[index]?.label || `第 ${index+1} 张`;}
function saveTarotForm() {
  sessionStorage.setItem('tarot-form',JSON.stringify({question:$('#tarotQuestion').value,background:$('#tarotBackground').value,spread_id:$('#tarotSpread').value,draw_source:$('#tarotSource').value,A:$('#tarotOptionA').value,B:$('#tarotOptionB').value,nextExplicit:tarotState.nextExplicit,previousDraw:tarotState.previousDraw,nextCaseId:tarotState.nextCaseId}));
}
function restoreTarotForm() {
  const saved=storedJson('tarot-form',{}),context=chatContext();
  if(!tarotState.draw){tarotState.nextExplicit=!!saved.nextExplicit;tarotState.previousDraw=saved.previousDraw || null;if(Object.prototype.hasOwnProperty.call(saved,'nextCaseId'))tarotState.nextCaseId=saved.nextCaseId;}
  const caseId=tarotState.nextCaseId===undefined?context.case_id:tarotState.nextCaseId,entry=tarotState.cases.find(c=>c.id===caseId);
  if(!$('#tarotQuestion').value)$('#tarotQuestion').value=saved.question || '';
  if(!$('#tarotBackground').value)$('#tarotBackground').value=saved.background || caseBackground(entry);
  if(saved.spread_id && tarotList(tarotState.deck?.spreads).some(s=>s.id===saved.spread_id))$('#tarotSpread').value=saved.spread_id;
  $('#tarotSource').value=['auto','pick','manual'].includes(saved.draw_source)?saved.draw_source:'auto';
  $('#tarotOptionA').value=saved.A || '';$('#tarotOptionB').value=saved.B || '';
  const savedReversals=localStorage.getItem('tarot-reversals');$('#tarotReversals').checked=savedReversals===null?tarotState.deck?.preferences?.reversals!==false:savedReversals!=='false';
  $('#tarotCaseHint').textContent=tarotState.nextCaseId===null?'':entry?'接着「'+entry.title+'」继续':context.case_id?'接着当前事项继续':'';
  updateTarotSettings();
}
function updateTarotSettings() {
  const spread=tarotSpread(),positions=tarotPositions(spread),isAB=positions.length===5,manual=$('#tarotSource').value==='manual';
  $('#tarotSpreadDescription').textContent=spread.description || positions.map(p=>p.label).join(' / ');
  $('#tarotAB').classList.toggle('hidden',!isAB);$('#tarotOptionA').required=isAB;$('#tarotOptionB').required=isAB;
  if(isAB)$('#tarotAdvanced').open=true;
  const previous=[...$('#tarotManual').querySelectorAll('.manual-card-row')].map(row=>({card_id:row.querySelector('[data-manual-card]').value,orientation:row.querySelector('[data-manual-orientation]').value}));
  $('#tarotManual').classList.toggle('hidden',!manual);
  if(manual)$('#tarotManual').innerHTML=manualCardsHtml(positions,previous);
  $('#tarotStartBtn').textContent=manual?'保存实体牌记录':$('#tarotSource').value==='pick'?'准备牌背，开始选牌':'开始梳理';
  saveTarotForm();
}
function manualCardsHtml(positions, selected=[], reversals=$('#tarotReversals').checked) {
  return positions.map((p,i)=>`<div class="manual-card-row"><label>${esc(p.label)}<select data-manual-card aria-label="${esc(p.label)}的牌" required><option value="">选择实际抽到的牌</option>${tarotList(tarotState.deck?.cards).map(c=>`<option value="${esc(c.card_id)}" ${selected[i]?.card_id===c.card_id?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label><label>方向<select data-manual-orientation aria-label="${esc(p.label)}的方向"><option value="upright">正位</option><option value="reversed" ${!reversals?'disabled':''} ${reversals && selected[i]?.orientation==='reversed'?'selected':''}>逆位</option></select></label></div>`).join('');
}
function readManualCards(root) {
  const cards=[...root.querySelectorAll('.manual-card-row')].map(row=>({card_id:row.querySelector('[data-manual-card]').value,orientation:row.querySelector('[data-manual-orientation]').value}));
  if(cards.some(c=>!c.card_id))throw Error('请逐张选择实际抽到的实体牌。');
  if(new Set(cards.map(c=>c.card_id)).size!==cards.length)throw Error('同一次牌阵不能重复录入同一张牌，请检查。');
  return cards;
}
async function loadTarot() {
  tarotStatus('正在读取牌库与已保存的抽牌…');
  const results=await Promise.allSettled([apiJson('/api/tarot/deck'),apiJson('/api/tarot/draws'),apiJson('/api/cases')]);
  if(results[0].status==='fulfilled' && Array.isArray(results[0].value.cards)) {
    tarotState.deck=results[0].value;
    $('#tarotSpread').innerHTML=tarotList(tarotState.deck.spreads).map(s=>`<option value="${esc(s.id)}" ${s.id==='reflect3'?'selected':''}>${esc(s.name || s.title || s.id)}${s.id==='reflect3'?'（推荐）':''}</option>`).join('');
    restoreTarotForm();$('#tarotStartBtn').disabled=false;
  } else {$('#tarotStartBtn').disabled=true;loaded.tarot=false;tarotStatus('牌库暂时无法读取，请稍后刷新。',true);return;}
  if(results[1].status==='fulfilled')tarotState.draws=tarotList(results[1].value);
  if(results[2].status==='fulfilled')tarotState.cases=tarotList(results[2].value);
  renderTarotHistory();restoreTarotForm();
  tarotStatus(results[1].status==='rejected'?'历史记录暂时无法读取；已保存的抽牌不会因此改变。':'',results[1].status==='rejected');
  const drawId=parseRoute().draw || sessionStorage.getItem('tarot-current-draw');
  if(drawId && currentPage==='tarot')await openTarotDraw(drawId,false);
}
function renderTarotHistory() {
  const select=$('#tarotCaseFilter'),current=select.value;
  select.innerHTML='<option value="">全部事项</option>'+tarotState.cases.map(c=>`<option value="${esc(c.id)}" ${current===c.id?'selected':''}>${esc(c.title)}</option>`).join('');
  const records=tarotState.draws.filter(d=>!select.value || d.case_id===select.value);
  $('#tarotHistory').innerHTML=records.length?records.map(d=>`<button class="tarot-history-item ${tarotState.draw?.id===d.id?'active':''}" data-tarot-draw="${esc(d.id)}"><span>${esc(d.question || '未命名的问题')}</span><small>${esc((d.created_at || d.at || '').slice(0,10))} · ${esc(({selecting:'继续选牌',pending:'继续选牌',pending_reveal:'继续翻牌',cancelled:'已结束',revealed:'已翻牌',drawn:'已抽牌',ready:'可继续解读'})[d.status] || '查看记录')}</small></button>`).join(''):'<p class="muted tarot-history-empty">还没有记录。从眼前的一个问题开始。</p>';
  $('#tarotHistory').querySelectorAll('[data-tarot-draw]').forEach(button=>button.onclick=()=>openTarotDraw(button.dataset.tarotDraw));
}
async function openTarotDraw(id, updateRoute=true) {
  if(!id)return;const version=++tarotState.loadVersion;
  if(currentPage!=='tarot')switchPage('tarot',true);
  if(updateRoute)history.pushState(null,'','#/tarot?draw='+encodeURIComponent(id));
  tarotStatus('正在恢复这次抽牌…');
  try {
    const draw=await apiJson('/api/tarot/draws/'+encodeURIComponent(id));
    if(version!==tarotState.loadVersion)return;
    tarotState.draw=draw;tarotState.readings=[];sessionStorage.setItem('tarot-current-draw',id);$('#tarotForm').classList.add('hidden');
    renderTarotDraw();renderTarotHistory();
    try {const versions=await apiJson('/api/tarot/draws/'+encodeURIComponent(id)+'/readings');if(version===tarotState.loadVersion){tarotState.readings=tarotList(versions);renderTarotReading();}}
    catch(e){if(version===tarotState.loadVersion)$('#tarotReadingRoot').innerHTML=`<p class="err-banner">解读版本暂时无法读取：${esc(e.message)}</p>`;}
    if(version===tarotState.loadVersion)tarotStatus('');
  } catch(e) {if(version===tarotState.loadVersion){tarotStatus('恢复未完成：'+e.message,true);if(e.status===404){sessionStorage.removeItem('tarot-current-draw');$('#tarotForm').classList.remove('hidden');}}}
}
async function submitTarot(event) {
  event?.preventDefault();if(tarotState.busy)return;
  const error=$('#tarotFormError');error.classList.add('hidden');
  try {
    const question=$('#tarotQuestion').value.trim(),spread=tarotSpread(),context=chatContext();if(tarotState.nextCaseId!==undefined)context.case_id=tarotState.nextCaseId;if(!question)throw Error('先写下这次想梳理的问题。');
    const isAB=tarotPositions(spread).length===5,options={A:$('#tarotOptionA').value.trim(),B:$('#tarotOptionB').value.trim()};
    if(isAB && (!options.A || !options.B)){$('#tarotAdvanced').open=true;throw Error('请先写清 A 与 B 分别是什么。');}
    const source=$('#tarotSource').value,body={question,spread_id:spread.id,draw_source:source,reversals:$('#tarotReversals').checked,options:isAB?options:{},background:$('#tarotBackground').value.trim(),subject_id:'self',explicit_new:tarotState.nextExplicit,...(context.case_id?{case_id:context.case_id}:{}),...(tarotState.previousDraw?{previous_draw_id:tarotState.previousDraw}:{})};
    if(source==='manual')body.manual_cards=readManualCards($('#tarotManual'));
    body.idempotency_key=tarotOperationKey('create',body);tarotState.busy=true;$('#tarotStartBtn').disabled=true;tarotStatus('正在保存问题并建立抽牌记录…');saveTarotForm();
    const response=await apiJson('/api/tarot/draws',{method:'POST',body:JSON.stringify(body)});
    if(!response.draw?.id)throw Error('服务器没有返回已保存的抽牌，请稍后重试。');
    clearTarotOperation('create');tarotState.nextExplicit=false;tarotState.previousDraw=null;saveTarotForm();
    const draw=response.draw;tarotState.draws=[draw,...tarotState.draws.filter(d=>d.id!==draw.id)];
    await openTarotDraw(draw.id);if(response.reused)tarotStatus('已恢复这件事原来的牌阵。可以补充新事实或继续讨论。');
  } catch(e){error.textContent=e.message;error.classList.remove('hidden');tarotStatus('尚未确认保存。重试会使用同一个请求，不会隐式重抽。',true);}
  finally{tarotState.busy=false;$('#tarotStartBtn').disabled=!tarotState.deck;}
}
function tarotCardHtml(card,index) {
  const label=tarotPositionName(card,index),revealed=card.revealed===true,entry=revealed?(card.card || tarotCard(card.card_id)):{},name=entry.name || card.name || card.card_id || '牌面';
  const orientation=tarotOrientation(card.orientation),image=tarotSafeImage(revealed?card.card_id:null);
  return `<article class="tarot-position ${revealed?'is-revealed':''}"><div class="tarot-position-label"><span>${index+1}</span><h3>${esc(label)}</h3></div><button class="tarot-card ${revealed?'revealed':''} ${tarotState.animatePositions.includes(card.position)?'animate-flip':''} ${tarotState.skipMotion?'no-motion':''}" data-reveal-position="${esc(card.position)}" ${revealed?'disabled':''} aria-label="${esc(revealed?label+'：'+name+'，'+orientation:'翻开'+label+'的牌')}"><img src="${image}" alt="${esc(revealed?name+' · 产品自制图形牌':'统一牌背')}" ${revealed&&card.orientation==='reversed'?'class="reversed"':''} loading="lazy">${revealed?'':'<span class="tarot-flip-hint">轻触翻牌</span>'}</button>${revealed?`<div class="tarot-card-name"><strong>${esc(name)}</strong><span>${orientation}</span></div><p class="tarot-theme">${esc(tarotText(card.orientation==='reversed'?(entry.reversed_theme || entry.reversed):(entry.upright_theme || entry.upright)))}</p><details class="tarot-card-notes"><summary>牌意与可思考的问题</summary><p>${esc(tarotText(entry.common_misreading || entry.misreading || entry.misreadings))}</p>${tarotList(entry.questions || entry.discussion_questions || (entry.question?[entry.question]:[])).map(q=>`<p>${esc(q)}</p>`).join('')}</details>`:'<p class="tarot-theme">牌已固定，翻牌不会改变结果。</p>'}</article>`;
}
function renderTarotDraw() {
  const draw=tarotState.draw,root=$('#tarotDrawRoot');if(!draw){root.innerHTML='';return;}
  const cards=tarotList(draw.cards),positions=tarotPositions(draw.spread),targetCount=positions.length || cards.length,allRevealed=cards.length===targetCount && cards.length>0 && cards.every(c=>c.revealed===true),cancelled=['cancelled','abandoned','deleted'].includes(draw.status),picking=draw.draw_source==='pick' && cards.length<targetCount && !cancelled;
  const source={auto:'应用随机抽牌',pick:'点选牌背',manual:'实体牌手动录入'}[draw.draw_source] || '抽牌记录';
  root.innerHTML=`<section class="tarot-result"><div class="tarot-result-heading"><div><span class="eyebrow">${esc(source)} · ${esc((draw.created_at || '').slice(0,10))}</span><h2 tabindex="-1">${esc(draw.question)}</h2><p>${esc(draw.spread?.name || draw.spread?.title || '')}${draw.reversals?' · 使用正逆位':' · 不使用逆位'}</p></div><button class="quiet-button" data-tarot-new>新问题</button></div>${draw.options?.A?`<div class="tarot-frozen-options"><p><b>A</b> ${esc(draw.options.A)}</p><p><b>B</b> ${esc(draw.options.B)}</p></div>`:''}${tarotBackground(draw)?`<details class="tarot-snapshot"><summary>本次问题背景</summary><p>${esc(tarotBackground(draw))}</p></details>`:''}${cancelled?'<p class="muted">这次选牌已结束。已有记录保留，可以查看或删除。</p>':''}
    ${picking?`<section class="tarot-pick-section"><h3>选第 ${cards.length+1} 张 · ${esc(positions[cards.length]?.label || '')}</h3><p class="muted">本次牌序已经固定。按顺序选择牌背，之后再翻开。</p><div class="tarot-backs" role="group" aria-label="可选择的牌背">${tarotList(draw.backs).map((back,i)=>{const id=typeof back==='string'?back:back.id || back.back_id;const selected=cards.some(c=>c.back_id===id);return `<button class="tarot-back ${selected?'selected':''}" data-select-back="${esc(id)}" ${selected?'disabled':''} aria-label="第 ${i+1} 张牌背${selected?'，已选择':''}"><img src="/static/tarot/back.svg" alt="" loading="lazy"><span>${selected?'已选':i+1}</span></button>`;}).join('')}</div></section>`:''}
    <div class="tarot-spread" data-card-count="${targetCount}" role="group" aria-label="本次牌阵">${cards.map(tarotCardHtml).join('')}</div>
    ${cards.length && !allRevealed && !cancelled && !picking?'<div class="tarot-reveal-actions"><button class="quiet-button" data-reveal-all>全部翻开 · 跳过动画</button></div>':''}
    ${allRevealed&&!cancelled?`<div class="tarot-reading-toolbar"><div><h3>把牌面放回现实</h3><p>解释可更新，这次抽到的牌不会改变。</p></div><button class="btn-gold" data-request-reading>生成 AI 解读</button></div><div id="tarotReadingStatus" class="muted" role="status" aria-live="polite"></div>`:''}<div id="tarotReadingRoot"></div>
    <div class="tarot-followups"><button class="quiet-button" data-tarot-chat>${allRevealed&&!cancelled?'继续讨论此牌阵':'回到对话讨论这件事'} ↗</button>${allRevealed&&!cancelled?'<button class="quiet-button" data-tarot-supplement>补充事实</button>':''}<button class="quiet-button" data-tarot-feedback>记录决定、行动或结果</button></div>
    <form id="tarotSupplementForm" class="tarot-note-form hidden"><label>还有哪些现实情况？<textarea id="tarotSupplement" rows="3" maxlength="4000" placeholder="补充你实际知道的条件；不会改变已经抽到的牌。">${esc(sessionStorage.getItem('tarot-supplement:'+draw.id) || '')}</textarea></label><button type="submit" class="btn-gold">用这些信息重新解读</button></form>
    <form id="tarotFeedbackForm" class="tarot-note-form hidden"><label>这次记录什么？<select id="tarotFeedbackKind"><option value="decided">我已经作出的决定</option><option value="acted">我实际采取的行动</option><option value="result">发生的结果</option><option value="completed">我已完成的事项</option><option value="rejected_interpretation">这段解释不符合我</option><option value="progress">其他进展</option></select></label><label>用你的话记录<textarea id="tarotFeedback" rows="3" maxlength="4000" placeholder="只记录你明确反馈的事情，不把考虑中的方案当作已经执行。" required></textarea></label><button type="submit" class="btn-gold">保存我的反馈</button><p id="tarotFeedbackStatus" class="muted" role="status"></p></form>
    <details class="tarot-record-options"><summary>记录管理</summary><p>新一轮会保留本次记录，并明确关联。重新生成解释不需要重新抽牌。</p><button class="quiet-button" data-tarot-new-explicit>明确开始新一轮</button>${!allRevealed&&!cancelled?'<button class="quiet-button" data-tarot-cancel>结束这次选牌</button>':''}${draw.draw_source==='manual'?'<button class="quiet-button" data-tarot-correct>更正实体牌录入</button>':''}<details class="delete-record"><summary>删除本次记录</summary><p>会删除本次问题、抽牌及关联解释；这不会删除整个事项或其他对话。</p><button class="quiet-button danger-button" data-tarot-delete>确认删除这次抽牌与解读</button></details></details><div id="tarotCorrectionRoot"></div></section>`;
  root.querySelectorAll('[data-reveal-position]').forEach(button=>{if(picking || cancelled)button.disabled=true;button.onclick=()=>mutateTarotDraw('reveal',{position:Number(button.dataset.revealPosition)});});
  root.querySelectorAll('[data-select-back]').forEach(button=>button.onclick=()=>mutateTarotDraw('select',{back_id:button.dataset.selectBack}));
  root.querySelector('[data-reveal-all]')?.addEventListener('click',()=>{tarotState.skipMotion=true;mutateTarotDraw('reveal',{});});
  root.querySelector('[data-request-reading]')?.addEventListener('click',()=>requestTarotReading());
  root.querySelector('[data-tarot-chat]').onclick=()=>continueTarotChat(draw);
  root.querySelector('[data-tarot-new]').onclick=()=>newTarotQuestion(false);
  root.querySelector('[data-tarot-new-explicit]').onclick=()=>newTarotQuestion(true);
  root.querySelector('[data-tarot-cancel]')?.addEventListener('click',()=>mutateTarotDraw('cancel',{}));
  root.querySelector('[data-tarot-delete]').onclick=deleteTarotDraw;
  root.querySelector('[data-tarot-correct]')?.addEventListener('click',showTarotCorrection);
  root.querySelector('[data-tarot-supplement]')?.addEventListener('click',()=>{$('#tarotSupplementForm').classList.remove('hidden');$('#tarotSupplement').focus();});
  root.querySelector('[data-tarot-feedback]').onclick=openTarotFeedback;
  $('#tarotSupplementForm').onsubmit=event=>{event.preventDefault();requestTarotReading($('#tarotSupplement').value.trim());};
  $('#tarotSupplement').oninput=()=>sessionStorage.setItem('tarot-supplement:'+draw.id,$('#tarotSupplement').value);
  $('#tarotFeedbackForm').onsubmit=saveTarotFeedback;
  root.querySelector('.tarot-backs')?.addEventListener('keydown',event=>{if(!['ArrowRight','ArrowLeft','ArrowDown','ArrowUp','Home','End'].includes(event.key))return;const buttons=[...root.querySelectorAll('[data-select-back]:not(:disabled)')],current=buttons.indexOf(event.target);if(current<0)return;event.preventDefault();const direction=['ArrowLeft','ArrowUp'].includes(event.key)?-1:1;const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(current+direction+buttons.length)%buttons.length;buttons[next]?.focus();});
  renderTarotReading();
  tarotState.animatePositions=[];
}
async function mutateTarotDraw(action, payload) {
  if(tarotState.busy || !tarotState.draw)return;const id=tarotState.draw.id;tarotState.busy=true;
  const operation=id+':'+action+':'+(payload.back_id ?? payload.position ?? 'all'),body={...payload};
  body.idempotency_key=tarotOperationKey(operation,payload);body.request_id=body.idempotency_key;
  $('#tarotDrawRoot').setAttribute('aria-busy','true');$('#tarotDrawRoot').querySelectorAll('[data-select-back],[data-reveal-position],[data-reveal-all]').forEach(b=>b.disabled=true);
  try {const draw=await apiJson('/api/tarot/draws/'+encodeURIComponent(id)+'/'+action,{method:'POST',body:JSON.stringify(body)});clearTarotOperation(operation);if(tarotState.draw?.id!==id)return;tarotState.animatePositions=tarotList(draw.cards).filter(c=>c.revealed && !tarotList(tarotState.draw.cards).some(old=>old.position===c.position && old.revealed)).map(c=>c.position);tarotState.draw=draw;renderTarotDraw();tarotStatus(action==='select'?'选牌已保存。':action==='cancel'?'本次选牌已结束。':'牌面已翻开并保存。');if(action==='select')$('#tarotDrawRoot [data-select-back]:not(:disabled)')?.focus();}
  catch(e){tarotStatus('操作未确认：'+e.message+'。重试会继续原来的抽牌。',true);if(tarotState.draw?.id===id)renderTarotDraw();}
  finally{tarotState.busy=false;$('#tarotDrawRoot').setAttribute('aria-busy','false');}
}
function renderTarotReading(selectedId) {
  const root=$('#tarotReadingRoot');if(!root)return;
  const versions=tarotState.readings,completed=versions.filter(v=>['success','complete','completed'].includes(v.status)),reading=completed.find(v=>v.id===selectedId) || completed.at(-1),latest=versions.at(-1);
  $('#tarotDrawRoot').querySelectorAll('.tarot-record-options button,[data-tarot-new]').forEach(b=>b.disabled=tarotState.reading);
  const button=$('[data-request-reading]');if(button){button.disabled=tarotState.reading;button.textContent=completed.length?'重新解读 · 不换牌':'生成 AI 解读';}
  if(reading?.result) {
    const result=reading.result;
    root.innerHTML=`<div class="tarot-version-row"><span>已保存的解读</span>${completed.length>1?`<label>版本 <select id="tarotReadingVersion" aria-label="查看解读版本">${completed.map((v,i)=>`<option value="${esc(v.id)}" ${v.id===reading.id?'selected':''}>第 ${v.version || i+1} 版</option>`).join('')}</select></label>`:''}</div><div class="msg-body tarot-reading">${answerHtml(result)}</div>`;
    $('#tarotReadingVersion')?.addEventListener('change',event=>renderTarotReading(event.target.value));
  } else root.innerHTML='<p class="tarot-static-note">可以先阅读牌面与反思问题。AI 解读会结合现实背景，成功保存后才会显示。</p>';
  if(latest && !['success','complete','completed'].includes(latest.status)) {
    const status=({pending:'解释正在准备，可以稍后刷新。',running:'解释仍在进行，可以稍后刷新。',unconfigured:'AI 解读未配置；抽牌与静态牌意仍可阅读。',not_configured:'AI 解读未配置；抽牌与静态牌意仍可阅读。',failed:'本次解释没有完成；已经保存的牌不变。',cancelled:'本次解释已停止；已经保存的牌不变。'})[latest.status] || '本次解释尚未成功保存。';
    root.insertAdjacentHTML('beforeend',`<p class="err-banner">${esc(status)}${latest.error?' '+esc(tarotText(latest.error)):''}</p>`);
  }
}
async function requestTarotReading(supplement='') {
  const draw=tarotState.draw;if(!draw || tarotState.reading)return;
  const operation=draw.id+':reading',payload={supplement},id=tarotOperationKey(operation,payload);tarotState.reading=true;renderTarotReading();
  const status=$('#tarotReadingStatus');if(status)status.textContent='正在结合这次牌阵与现实信息…';
  let received=false,readingError='',readingId='';
  try {
    let run,response;
    try{run=await apiJson('/api/runs/'+encodeURIComponent('reading:'+id));}catch(e){if(e.status!==404)throw e;}
    if(run?.status==='succeeded'){received=true;clearTarotOperation(operation);await openTarotDraw(draw.id,false);return;}
    if(run && ['failed','stale'].includes(run.status))response=await api('/api/runs/'+encodeURIComponent(run.id)+'/retry',{method:'POST',body:JSON.stringify({request_id:'retry:'+run.operation_id})});
    else response=await api('/api/tarot/draws/'+encodeURIComponent(draw.id)+'/readings',{method:'POST',body:JSON.stringify({request_id:id,supplement})});
    if(!response.ok){let problem=await response.json().catch(()=>({}));throw Error(problem.detail || `解读服务暂不可用 (${response.status})`);}
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
    const accept=line=>{if(!line.startsWith('data:'))return;const data=line.slice(5).trim();if(!data || data==='[DONE]')return;const event=JSON.parse(data);if(event.type==='started')readingId=event.reading_id || '';if((event.type==='status' || event.type==='started') && status)status.textContent=event.text || '解读正在进行…';if(event.type==='error')readingError=event.message || event.error || '解释未完成';if(event.type==='result'){received=true;readingId=event.reading_id || readingId;if(tarotState.draw?.id===draw.id){tarotState.readings.push({id:readingId || id,status:'success',result:event.result});renderTarotReading();}}};
    while(true){const packet=await reader.read();if(packet.done){buffer+=decoder.decode();if(buffer.trim())accept(buffer.trim());break;}buffer+=decoder.decode(packet.value,{stream:true});let pos;while((pos=buffer.indexOf('\n'))>=0){accept(buffer.slice(0,pos).trim());buffer=buffer.slice(pos+1);}}
    if(readingError)throw Error(String(readingError));
    if(!received)throw Error('连接中断或解释尚未完成');
    clearTarotOperation(operation);if(status)status.textContent='解读已保存。这次抽到的牌保持不变。';
  } catch(e) {
    try {const versions=tarotList(await apiJson('/api/tarot/draws/'+encodeURIComponent(draw.id)+'/readings'));if(tarotState.draw?.id===draw.id){tarotState.readings=versions;renderTarotReading();}const own=versions.find(v=>v.id===readingId || v.request_id===id);if(own && ['success','complete','completed'].includes(own.status)){received=true;clearTarotOperation(operation);}}catch {}
    if(status)status.textContent=received?'已找回并保存解读，牌阵没有变化。':'解释未完成：'+e.message+'。牌阵已保留；可刷新记录或重试解释。';
  } finally {tarotState.reading=false;if(tarotState.draw?.id===draw.id)renderTarotReading();}
}
function continueTarotChat(draw) {
  const cards=tarotList(draw.cards),ready=cards.length===tarotPositions(draw.spread).length && cards.length>0 && cards.every(c=>c.revealed===true) && !['cancelled','abandoned','deleted'].includes(draw.status);
  setChatContext({case_id:draw.case_id,...(ready?{draw_id:draw.id}:{}),title:draw.question});switchPage('chat');$('#chatInput').focus();toast(ready?'已关联这次牌阵，可以直接接着问。':'已关联这件事，完成翻牌后可接着讨论牌面。');
}
function newTarotQuestion(explicit=false) {
  if(tarotState.reading || tarotState.busy){toast('请等当前操作结束，再开始新问题。');return;}
  const previous=tarotState.draw;tarotState.previousDraw=explicit?previous?.id || null:null;tarotState.nextCaseId=explicit?previous?.case_id || null:null;tarotState.nextExplicit=explicit;tarotState.draw=null;tarotState.readings=[];tarotState.skipMotion=false;
  sessionStorage.removeItem('tarot-current-draw');history.pushState(null,'','#/tarot');$('#tarotForm').classList.remove('hidden');$('#tarotDrawRoot').innerHTML='';
  if(explicit && previous){$('#tarotSpread').value=previous.spread_id || previous.spread?.id || 'reflect3';$('#tarotSource').value=previous.draw_source || 'auto';$('#tarotReversals').checked=previous.reversals!==false;}
  $('#tarotOptionA').value=explicit?previous?.options?.A || '':'';$('#tarotOptionB').value=explicit?previous?.options?.B || '':'';$('#tarotManual').innerHTML='';
  $('#tarotQuestion').value=explicit?previous?.question || '':'';$('#tarotBackground').value=explicit?tarotBackground(previous):'';$('#tarotCaseHint').textContent=explicit?'接着同一事项，建立新一轮':'';updateTarotSettings();tarotStatus(explicit?'将建立新一轮记录，原牌阵会保留并关联。':'');$('#tarotQuestion').focus();
}
async function deleteTarotDraw() {
  const draw=tarotState.draw;if(!draw || tarotState.busy)return;tarotState.busy=true;
  try {const result=await writeJson('/api/tarot/draws/'+encodeURIComponent(draw.id),{},'DELETE');const ids=tarotList(result.deleted_ids).length?result.deleted_ids:[draw.id];tarotState.draws=tarotState.draws.filter(d=>!ids.includes(d.id));for(const id of ids){sessionStorage.removeItem('tarot-supplement:'+id);for(let i=sessionStorage.length-1;i>=0;i--){const key=sessionStorage.key(i);if(key?.startsWith('tarot-request:'+id+':'))sessionStorage.removeItem(key);}}tarotState.busy=false;const context=chatContext();if(ids.includes(context.draw_id))setChatContext({case_id:context.case_id,title:'当前事项'});newTarotQuestion(false);tarotState.previousDraw=null;renderTarotHistory();toast('这次抽牌与解读已删除');}
  catch(e){tarotStatus('删除未成功：'+e.message,true);}finally{tarotState.busy=false;}
}
function showTarotCorrection() {
  const draw=tarotState.draw,root=$('#tarotCorrectionRoot');
  root.innerHTML=`<form id="tarotCorrectionForm" class="tarot-note-form"><h3>更正实体牌录入</h3><p class="muted">仅用于修正录入错误，保留修订痕迹；原来的解释需要重新生成。</p>${manualCardsHtml(tarotPositions(draw.spread),draw.cards,draw.reversals)}<label>更正原因<textarea id="tarotCorrectionReason" rows="2" maxlength="800" required></textarea></label><button type="submit" class="btn-gold">保存录入更正</button></form>`;
  $('#tarotCorrectionForm').onsubmit=async event=>{event.preventDefault();if(tarotState.busy)return;try {const reason=$('#tarotCorrectionReason').value.trim();if(!reason)throw Error('请写明哪里录入有误。');const body={cards:readManualCards(root),reason};body.idempotency_key=tarotOperationKey(draw.id+':manual',body);tarotState.busy=true;const updated=await apiJson('/api/tarot/draws/'+encodeURIComponent(draw.id)+'/manual',{method:'PATCH',body:JSON.stringify(body)});clearTarotOperation(draw.id+':manual');tarotState.draw=updated;tarotState.draws=[updated,...tarotState.draws.filter(d=>d.id!==updated.id)];tarotState.readings=[];sessionStorage.setItem('tarot-current-draw',updated.id);history.pushState(null,'','#/tarot?draw='+encodeURIComponent(updated.id));if(chatContext().draw_id===draw.id)setChatContext({...chatContext(),draw_id:updated.id});renderTarotDraw();renderTarotHistory();tarotStatus('实体牌录入已更正，旧解释不作为当前牌面的解读。');}catch(e){tarotStatus(e.message,true);}finally{tarotState.busy=false;}};
}
async function openTarotFeedback() {
  const form=$('#tarotFeedbackForm'),draw=tarotState.draw;if(!form || !draw)return;
  form.classList.remove('hidden');$('#tarotFeedback').focus();
  if(form.dataset.revision!==undefined)return;
  const button=form.querySelector('button'),status=form.querySelector('[role=status]');button.disabled=true;status.textContent='正在读取事项版本…';
  try {const cases=await apiJson('/api/cases'),entry=cases.find(c=>c.id===draw.case_id);form.dataset.revision=String(entityRevision(entry));status.textContent='只会保存你明确提交的这段话。';}
  catch(e){status.textContent='暂时无法读取事项：'+e.message;}
  finally{button.disabled=false;}
}
async function saveTarotFeedback(event) {
  event.preventDefault();const draw=tarotState.draw,content=$('#tarotFeedback').value.trim(),status=$('#tarotFeedbackStatus');if(!content)return;
  if(!draw.case_id){status.textContent='这条抽牌还没有关联事项，请回到对话补充情况后再记录。';return;}
  const form=$('#tarotFeedbackForm'),button=form.querySelector('button'),body={kind:$('#tarotFeedbackKind').value,content};if(button.disabled)return;body.request_id=tarotOperationKey(draw.id+':feedback',body);button.disabled=true;
  try {if(form.dataset.revision===undefined){const cases=await apiJson('/api/cases'),entry=cases.find(c=>c.id===draw.case_id);form.dataset.revision=String(entityRevision(entry));}body.expected_revision=Number(form.dataset.revision);await apiJson('/api/cases/'+encodeURIComponent(draw.case_id)+'/events',{method:'POST',body:JSON.stringify(body)});clearTarotOperation(draw.id+':feedback');status.textContent='你的反馈已保存到这个事项。';form.querySelector('textarea').value='';delete form.dataset.revision;loaded.memory=false;loaded.cases=false;}
  catch(e){status.textContent=e.status===409?'事项在你填写期间有更新，反馈尚未保存。请刷新记录、核对情况后重新提交。':'反馈尚未保存：'+e.message;}finally{button.disabled=false;}
}
$('#tarotForm').onsubmit=submitTarot;
$('#tarotSpread').onchange=updateTarotSettings;$('#tarotSource').onchange=updateTarotSettings;
$('#tarotReversals').onchange=()=>{localStorage.setItem('tarot-reversals',String($('#tarotReversals').checked));updateTarotSettings();};
['#tarotQuestion','#tarotBackground','#tarotOptionA','#tarotOptionB'].forEach(selector=>$(selector).addEventListener('input',saveTarotForm));
$('#tarotCaseFilter').onchange=renderTarotHistory;$('#tarotRefreshBtn').onclick=loadTarot;
$('#chatTarotBtn').onclick=()=>{
  const context=chatContext(),message=$('#chatInput').value.trim();
  if(context.draw_id && !message){openTarotDraw(context.draw_id);return;}
  const entry=tarotState.cases.find(c=>c.id===context.case_id);tarotState.nextCaseId=context.case_id || null;tarotState.nextExplicit=false;tarotState.previousDraw=null;
  $('#tarotQuestion').value=message || entry?.goal || entry?.state?.goal || entry?.title || '';
  $('#tarotBackground').value=caseBackground(entry);sessionStorage.removeItem('tarot-current-draw');tarotState.draw=null;$('#tarotForm').classList.remove('hidden');$('#tarotDrawRoot').innerHTML='';saveTarotForm();switchPage('tarot');restoreTarotForm();
};

/* ---- hash 路由：报告日期与固定 draw 可直接恢复 ---- */
let pendingReportDate = "";
function parseRoute() {
  const m=/^#\/([a-z]+)\/?(?:\?(.*))?$/.exec(location.hash || '#/chat');
  const page=m && loaders[m[1]]?m[1]:'chat',params=new URLSearchParams(m?.[2] || '');
  const date=params.get('date') || '',draw=params.get('draw') || '';return {page,date:/^\d{4}-\d{2}-\d{2}$/.test(date)?date:'',draw:/^[a-zA-Z0-9_-]{1,120}$/.test(draw)?draw:''};
}
function applyRoute() {const r=parseRoute();pendingReportDate=r.date;switchPage(r.page,true);if(r.page==='reports' && loaded.reports && r.date)locateReport(r.date);if(r.page==='tarot' && tarotState.deck && r.draw && tarotState.draw?.id!==r.draw)openTarotDraw(r.draw,false);}
window.addEventListener("hashchange", applyRoute);

/* ================= 搜索、记忆与初始化 ================= */
function readableSource(value, depth=0) {
  if(depth>5 || value==null)return '';
  if(typeof value==='string') {const text=value.trim();if(/^[\[{]/.test(text)){try{return readableSource(JSON.parse(text),depth+1);}catch {return '<p>这段来源暂时无法完整显示。</p>';}}return `<p>${esc(value)}</p>`;}
  if(Array.isArray(value))return value.map(item=>readableSource(item,depth+1)).join('');
  if(typeof value!=='object')return '';
  const author=({user:'你',assistant:'明镜',tool:'计算工具'})[value.role || value.author] || '',date=value.at || value.recorded_at || value.created_at || value.date || '';
  const content=value.quote ?? value.content ?? value.text ?? value.excerpt ?? value.body;
  if(content!==undefined)return `${value.usable_for_context===false?'<p class="source-retired-note">这段原文保留供你查看，已停止用于后续分析。</p>':''}${author || date?`<small>${esc(author)} ${esc(String(date).slice(0,16).replace('T',' '))}</small>`:''}${readableSource(content,depth+1)}`;
  for(const key of ['sources','source','records','messages','data'])if(value[key]!==undefined)return readableSource(value[key],depth+1);
  return '<p>来源可追溯，但没有可展示的原文节选。</p>';
}
async function loadCases(snapshot) {
  const root=$('#casesRoot');
  try {
    if(snapshot===undefined)snapshot=await apiJson('/api/state').catch(()=>null);
    const records=tarotList(await apiJson('/api/cases')).map(c=>({...c,goal:c.goal ?? c.state?.goal ?? '',events:c.events || snapshot?.cases?.find(x=>x.id===c.id)?.events || []}));tarotState.cases=records;
    root.innerHTML=records.length?records.map(c=>`<article class="case-card ${c.status==='closed'?'closed':''}" data-case-id="${esc(c.id)}"><div class="case-card-heading"><h3>${esc(c.title)}</h3><span>${c.status==='closed'?'已关闭':'进行中'}</span></div>${c.goal?`<p>${esc(c.goal)}</p>`:''}${c.events.length?`<details class="case-events"><summary>已记录的决定与进展</summary>${c.events.slice(-8).map(e=>`<p><small>${esc(({decided:'已作决定',acted:'已采取行动',action_started:'已采取行动',completed:'已完成',result:'结果反馈',feedback:'反馈',progress:'进展',discussed:'进展',rejected_interpretation:'解释不符合'})[e.kind] || '记录')} · ${esc((e.occurred_at || e.recorded_at || '').slice(0,10))}</small><br>${esc(e.content)}</p>`).join('')}</details>`:''}<div class="case-actions"><button class="quiet-button case-chat">继续聊这件事</button><button class="quiet-button case-tarot">用塔罗梳理</button></div><details><summary>事项设置</summary><label>名称<input class="case-title-input" value="${esc(c.title)}" maxlength="200"></label><label>目标<textarea class="case-goal-input" rows="2" maxlength="2000">${esc(c.goal || '')}</textarea></label><div class="case-actions"><button class="quiet-button case-save">保存更正</button><button class="quiet-button case-close">${c.status==='closed'?'重新打开事项':'关闭事项'}</button></div></details></article>`).join(''):'<p class="muted">还没有正在跟进的事项。可以自然地开始聊天，或在这里记下一件事。</p>';
    root.querySelectorAll('.case-card').forEach(card=>{
      const entry=records.find(c=>c.id===card.dataset.caseId);
      const patch=async changes=>{card.querySelectorAll('button').forEach(b=>b.disabled=true);try{await writeJson('/api/cases/'+encodeURIComponent(entry.id),{changes,expected_revision:entityRevision(entry)},'PATCH');toast('事项已更新');await loadCases();}catch(e){toast(e.status===409?'事项刚有更新，请刷新后核对再保存。':e.message);card.querySelectorAll('button').forEach(b=>b.disabled=false);}};
      card.querySelector('.case-chat').onclick=()=>{setChatContext({case_id:entry.id,title:entry.title});switchPage('chat');$('#chatInput').focus();};
      card.querySelector('.case-tarot').onclick=()=>{setChatContext({case_id:entry.id,title:entry.title});tarotState.nextCaseId=entry.id;tarotState.nextExplicit=false;tarotState.previousDraw=null;$('#tarotQuestion').value=entry.goal || entry.title;$('#tarotBackground').value=caseBackground(entry);saveTarotForm();sessionStorage.removeItem('tarot-current-draw');tarotState.draw=null;$('#tarotForm').classList.remove('hidden');$('#tarotDrawRoot').innerHTML='';switchPage('tarot');restoreTarotForm();};
      card.querySelector('.case-save').onclick=()=>patch({title:card.querySelector('.case-title-input').value.trim(),goal:card.querySelector('.case-goal-input').value.trim()});
      card.querySelector('.case-close').onclick=()=>patch({status:entry.status==='closed'?'open':'closed'});
    });
  } catch(e){root.innerHTML=`<p class="err-banner">事项暂时无法读取：${esc(e.message)}</p>`;}
}
function memoryFieldEditor(memory) {
  if(!memory.field)return '';
  const key=memory.field.split('.').at(-1),label=memory.field.endsWith('location.name')?'出生地点':({solar_datetime:'出生日期与时间',timezone_offset:'出生时区',time_uncertainty_minutes:'出生时间误差（分钟）',lng:'出生地点经度',lat:'出生地点纬度',date:'出生日期',time:'出生时间',year:'出生年份',month:'出生月份',day:'出生日期中的日',hour:'出生小时',minute:'出生分钟',city:'出生城市',place:'出生地点',latitude:'纬度',longitude:'经度',timezone:'时区',time_unknown:'出生时间是否未知',calendar:'历法',gender:'性别',name:'姓名'})[key] || '资料值';
  const simple=['string','number','boolean'].includes(typeof memory.value),value=typeof memory.value==='boolean'?(memory.value?'True':'False'):String(memory.value ?? '');
  return `<div class="memory-field-editor"><p>现有${esc(label)}：${simple?esc(value):'请回到对话核对具体内容'}</p>${simple?`<label>更正后的${esc(label)}${typeof memory.value==='boolean'?'<select class="memory-field-value" aria-label="更正后的资料值"><option value="">请选择</option><option value="True">是（True）</option><option value="False">否（False）</option></select>':`<input class="memory-field-value" type="${typeof memory.value==='number'?'number':'text'}" ${typeof memory.value==='number'?'step="any"':''} maxlength="200" placeholder="请填写更正后的值" aria-label="更正后的资料值">`}</label><p class="muted">请在上方更正原话中写明这个新值，便于日后核对。</p><label class="memory-field-consent"><input type="checkbox" class="memory-confirm-field"> 我确认这项资料，并同意用它更新后续分析。</label>`:'<p class="muted">这项资料需要逐项确认，请在对话中说明更正内容。</p>'}</div>`;
}
function memoryCorrection(card,memory) {
  const text=card.querySelector('textarea').value.trim();if(!text)throw Error('请写下更正后的内容。');const body={text};
  if(memory.field){const input=card.querySelector('.memory-field-value');if(!input)throw Error('请回到对话逐项确认这项资料。');if(!input.value.trim())throw Error('请单独填写更正后的资料值。');if(!card.querySelector('.memory-confirm-field')?.checked)throw Error('请确认资料正确并勾选更新授权。');const raw=input.value.trim();if(!text.includes(raw))throw Error('更正原话中也需要写明新值：'+raw);body.value=typeof memory.value==='number'?Number(raw):typeof memory.value==='boolean'?raw==='True':raw;if(typeof body.value==='number'&&!Number.isFinite(body.value))throw Error('请填写有效的数值。');}
  return body;
}
async function loadMemories() {
  const root=$('#memoriesRoot');root.innerHTML='<p class="muted">正在读取记忆…</p>';
  try {
    const snapshot=await apiJson('/api/state').catch(()=>null);renderMemorySettings(snapshot);
    const list=(await apiJson('/api/memories')).filter(m=>m.status!=='deleted');
    root.innerHTML=list.length?list.map(m=>`<article class="memory-card ${m.status!=='active'?'inactive':''}" data-id="${esc(m.id)}"><div class="memory-meta"><span>${esc(m.category || m.kind || '个人记录')}</span><span>${esc((m.valid_from || m.created_at || m.recorded_at || '').slice(0,10))} · ${m.status==='active'?'正在使用':m.status==='superseded'?'已被更正':m.status==='pending'?'待你确认':'已停用'}</span></div><textarea aria-label="记忆内容" rows="3" maxlength="2000">${esc(m.text || m.content || '')}</textarea>${memoryFieldEditor(m)}<details><summary>查看来源与修改记录</summary><div class="memory-source">${m.quote?`<p>${esc(m.quote)}</p>`:'<p>展开后可读取仍保留的原始来源。</p>'}</div><div class="memory-audit"></div><div class="memory-actions"><button class="quiet-button source-memory">查看原始来源</button><button class="quiet-button audit-memory">查看修改记录</button></div></details><div class="memory-actions"><button class="quiet-button save-memory" ${m.status!=='active'?'disabled':''}>保存更正</button>${m.status==='active'?'<button class="quiet-button toggle-memory">停用这条记忆</button>':'<span class="muted">如需再次使用，请在对话中用新原话确认。</span>'}</div><details class="delete-record"><summary>删除范围</summary><label>删除什么？<select class="memory-delete-scope"><option value="fact">只忘记这条事实，保留原始聊天</option><option value="source">同时删除原始来源及关联内容</option></select></label><p>删除后不再从这条来源重新恢复该事实。删除原始来源也可能影响关联的其他记录。</p><button class="quiet-button danger-button delete-memory">确认删除所选范围</button></details></article>`).join(''):emptyState('记','还没有长期记忆','明确告诉明镜你的背景、偏好或目标；保存后可在这里更正。');
    root.querySelectorAll('.memory-card').forEach(card=>{
      const m=list.find(x=>x.id===card.dataset.id);
      const patch=async data=>{card.querySelectorAll('button').forEach(b=>b.disabled=true);try{await writeJson('/api/memories/'+encodeURIComponent(m.id),{...data,expected_revision:entityRevision(m)},'PATCH');toast('记忆已更新');await loadMemories();}catch(e){toast(e.status===409?'记忆刚有更新，请刷新后核对再保存。':e.message);card.querySelectorAll('button').forEach(b=>b.disabled=false);}};
      card.querySelector('.save-memory').onclick=()=>{try{patch(memoryCorrection(card,m));}catch(e){toast(e.message);}};
      card.querySelector('.toggle-memory')?.addEventListener('click',()=>patch({status:'hidden'}));
      card.querySelector('.source-memory').onclick=async()=>{try{const data=await apiJson('/api/memories/'+encodeURIComponent(m.id)+'/source');card.querySelector('.memory-source').innerHTML=readableSource(data) || '<p>原始来源已不可用。</p>';}catch(e){card.querySelector('.memory-source').innerHTML=`<p>${esc(e.message || '来源暂时不可用')}</p>`;}};
      card.querySelector('.audit-memory').onclick=async()=>{try{const rows=await apiJson('/api/memories/'+encodeURIComponent(m.id)+'/audit');card.querySelector('.memory-audit').innerHTML=rows.length?rows.map(r=>`<p>${esc(r.at || r.created_at || '')} · ${esc(({created:'记录',updated:'更正',hidden:'停用',deleted:'删除',active:'恢复'})[r.action || r.operation] || '记录已修订')}${r.revision?' · 第 '+esc(r.revision)+' 次修订':''}</p>`).join(''):'<p>尚无修改记录</p>';}catch(e){toast(e.message);}};
      card.querySelector('.delete-memory').onclick=async()=>{const scope=card.querySelector('.memory-delete-scope').value,revision=entityRevision(m);card.querySelectorAll('button').forEach(b=>b.disabled=true);try{await writeJson('/api/memories/'+encodeURIComponent(m.id)+'?scope='+encodeURIComponent(scope)+'&expected_revision='+encodeURIComponent(revision),{expected_revision:revision,scope},'DELETE');toast(scope==='source'?'记忆与原始来源已删除':'已忘记这条事实');await loadMemories();if(scope==='source')loadHistory();}catch(e){toast('删除未成功：'+e.message);card.querySelectorAll('button').forEach(b=>b.disabled=false);}};
    });
  } catch(e){root.innerHTML=errState(e.message,'loadMemories');}
}
$('#refreshMemoriesBtn').onclick=loadMemories;
$('#refreshCasesBtn').onclick=()=>loadCases();
$('#newCaseBtn').onclick=()=>{$('#newCaseForm').classList.toggle('hidden');if(!$('#newCaseForm').classList.contains('hidden'))$('#newCaseTitle').focus();};
$('#newCaseForm').onsubmit=async event=>{event.preventDefault();const title=$('#newCaseTitle').value.trim();if(!title)return;const body={title,goal:$('#newCaseGoal').value.trim(),subject_id:'self'};body.request_id=tarotOperationKey('create-case',body);const button=$('#newCaseForm').querySelector('button');button.disabled=true;try{const result=await apiJson('/api/cases',{method:'POST',body:JSON.stringify(body)});clearTarotOperation('create-case');const entry=result.case || result;if(entry.id)setChatContext({case_id:entry.id,title:entry.title});$('#newCaseForm').reset();$('#newCaseForm').classList.add('hidden');await loadCases();toast('事项已保存');}catch(e){toast('事项尚未保存：'+e.message);}finally{button.disabled=false;}};
$('#openSearchBtn').onclick=()=>{rememberFocus('search');$('#searchModal').classList.remove('hidden');$('#globalSearchInput').focus();};
function closeSearch(){ $('#searchModal').classList.add('hidden');restoreFocus('search'); }
$('#closeSearchBtn').onclick=closeSearch;
let searchTimer,searchVersion=0;
$('#globalSearchInput').addEventListener('input',()=>{
  clearTimeout(searchTimer);const version=++searchVersion,q=$('#globalSearchInput').value.trim();
  if(!q){$('#searchResults').innerHTML='<p class="muted">试试描述一段经历，而不必记得原来的用词。</p>';return;}
  $('#searchResults').innerHTML='<p class="muted">正在检索…</p>';
  searchTimer=setTimeout(async()=>{try{const rows=await apiJson('/api/search?q='+encodeURIComponent(q));if(version!==searchVersion)return;
    $('#searchResults').innerHTML=rows.length?rows.map(r=>`<article class="search-result"><small>${esc(r.source)} · ${esc(r.date || '')}</small>${readableSource(r.text || r.data)}</article>`).join(''):emptyState('寻','暂未找到足够相关的记录','换一种描述，或缩小问题范围。');
  }catch(e){if(version===searchVersion)$('#searchResults').innerHTML=`<p class="err-banner">${esc(e.message)}</p>`;}},350);
});
document.addEventListener('keydown',e=>{
  if((e.ctrlKey || e.metaKey) && e.key.toLowerCase()==='k'){e.preventDefault();$('#openSearchBtn').click();}
  if(e.key==='Escape'){closeSearch();closeImageViewer();closeDrawer();}
});
$('#logoutBtn').onclick=()=>{localStorage.removeItem(TOKEN_KEY);localStorage.removeItem('mjt_session');sessionStorage.clear();for(const u of blobImages.values())URL.revokeObjectURL(u);location.reload();};
async function unlocked() {
  Object.keys(loaded).forEach(k=>delete loaded[k]);await loadSessions();loadHistory();loadSidebar();switchPage(currentPage,true);
}
async function authenticate(v) {
  if(!v.trim())return;saveToken(v);$('#tokenErr').classList.add('hidden');
  try{await apiJson('/api/health');closeTokenModal();$('#tokenModalInput').value='';await unlocked();}
  catch(e){openTokenModal(true);}
}
$('#tokenModalBtn').onclick=()=>authenticate($('#tokenModalInput').value);
$('#tokenSaveBtn').onclick=()=>authenticate($('#tokenInput').value);
$('#tokenModalInput').addEventListener('keydown',e=>{if(e.key==='Enter')$('#tokenModalBtn').click();});
$('#tokenInput').addEventListener('keydown',e=>{if(e.key==='Enter')$('#tokenSaveBtn').click();});
$('#todayLabel').textContent=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'long',day:'numeric',weekday:'long'}).format(new Date());
$('#chatInput').value=sessionStorage.getItem('draft:'+currentSession)||'';
renderChatContext();
applyRoute();
if(getToken())unlocked().catch(e=>toast(e.message));else openTokenModal(false);

document.addEventListener('keydown',e=>{
 if((e.key==='Enter' || e.key===' ') && e.target.matches('.chart-click,.zw-cell,.tl-card[onclick]')){e.preventDefault();e.target.click();}
 if(e.key==='Tab') {
   const dialog=['#tokenModal','#searchModal','#drawer'].map(x=>$(x)).find(el=>el && !el.classList.contains('hidden') && (el.id!=='drawer' || el.classList.contains('open')) && el.getClientRects().length);
   if(dialog){const items=[...dialog.querySelectorAll('button,input,textarea,select,a[href],[tabindex="0"]')].filter(el=>!el.disabled && el.getClientRects().length);const first=items[0],last=items.at(-1);if(items.length && (e.shiftKey && (document.activeElement===first || !dialog.contains(document.activeElement)))){e.preventDefault();last.focus();}else if(items.length && !e.shiftKey && (document.activeElement===last || !dialog.contains(document.activeElement))){e.preventDefault();first.focus();}}
 }
});
const accessibilityObserver=new MutationObserver(()=>{document?.querySelectorAll('.chart-click:not([tabindex]),.zw-cell:not([tabindex]),.tl-card[onclick]:not([tabindex])').forEach(el=>{if(el.hasAttribute('onclick')){el.tabIndex=0;el.setAttribute('role','button');}});});
accessibilityObserver.observe(document.querySelector('main'),{childList:true,subtree:true});
function updateKeyboardViewport(){
  const viewport=window.visualViewport;if(!viewport)return;
  const editing=document.activeElement?.matches('input,textarea,select'),open=editing && window.innerHeight-viewport.height>150;
  document.body.classList.toggle('keyboard-open',!!open);
  document.documentElement.style.setProperty('--visible-height',viewport.height+'px');
}
window.visualViewport?.addEventListener('resize',updateKeyboardViewport);
document.addEventListener('focusin',updateKeyboardViewport);document.addEventListener('focusout',()=>setTimeout(updateKeyboardViewport,0));

