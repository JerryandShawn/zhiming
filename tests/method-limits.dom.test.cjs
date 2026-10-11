// Rendering contract fixture only; this does not fake a business calculation.
const fs=require('fs'),assert=require('node:assert/strict'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync('static/index.html','utf8'),{url:'https://fixture.invalid/',runScripts:'outside-only'}),w=dom.window;
w.HTMLCanvasElement.prototype.getContext=()=>({});w.ResizeObserver=class{observe(){}disconnect(){}};
w.TextDecoder=TextDecoder;w.TextEncoder=TextEncoder;
w.eval(fs.readFileSync('static/vendor/marked.js','utf8'));w.eval(fs.readFileSync('static/vendor/purify.js','utf8'));
const code=fs.readFileSync('static/app.js','utf8').split("$('#todayLabel').textContent=")[0],functions=[...code.matchAll(/^(?:async )?function (\w+)/gm)].map(match=>match[1]);
w.eval(code+'\nObject.assign(window,{'+functions.join(',')+'});');
const result={answer:'先核实现实条件。',caveats:[],coverage_gaps:[{system:'astro',status:'RULE_GAP',reason:'年度连续搜索尚无已发布规则',issues:[{code:'RULE_GAP',detail:'不能挪用目标日快照'}]},
 {system:'bazi',status:'unsupported',reason:'复杂用神尚未实现<script>window.pwned=1</script>',issues:[]}],calculation_errors:[{system:'ziwei',code:'MISSING_INPUT',reason:'所需性别计算参数尚未确认。'}],
 calculation_fallbacks:[{system:'astro',requested:'Swiss Ephemeris',actual:'Moshier',body:'月亮',layer:'natal',returned_flags:260,private_input:'DO_NOT_RENDER_INPUT',owner_user_id:'DO_NOT_RENDER_OWNER'}]};
const host=w.document.createElement('div');w.document.body.append(host);host.innerHTML=w.answerHtml(result);
assert.equal(host.querySelector('details.answer-sources').open,false);
assert.match(host.querySelector('.answer-method-limits').textContent,/RULE_GAP.*年度连续搜索.*不能挪用目标日快照/);
assert.match(host.querySelector('.answer-method-limits').textContent,/unsupported.*复杂用神尚未实现/);
assert.match(host.querySelector('.calculation-error').textContent,/紫微斗数.*MISSING_INPUT.*尚未确认/);
assert.match(host.querySelector('.calculation-fallback').textContent,/Swiss Ephemeris → Moshier.*月亮.*本命.*260/);
assert.equal(host.querySelector('script'),null);assert.equal(w.pwned,undefined);
assert.doesNotMatch(host.textContent,/DO_NOT_RENDER/);
const chart={core_meta:{branches:[{coverage:'exact_input',civil_datetime:'2000-01-01 08:00'}],profiles:{a:{school_id:'synthetic-render-contract',actual_method:{ephemeris:['Moshier']},versions:{engine:'synthetic-only'},warnings:[],fallback:result.calculation_fallbacks}}}};
host.innerHTML=w.chartMetadata(chart);assert.match(host.querySelector('.chart-method').textContent,/实际回退：Swiss Ephemeris → Moshier.*月亮.*本命/);assert.doesNotMatch(host.textContent,/DO_NOT_RENDER/);
host.innerHTML=w.answerHtml({answer:'现有资料足够讨论一个小步骤。',caveats:[]});assert.equal(host.querySelector('.answer-method-limits'),null);
console.log('PASS: actual diagnostic fields render without model caveats; RULE_GAP, unsupported, calculation errors and explicit ephemeris fallback remain escaped, readonly and in the expandable professional limits');
dom.window.close();
