"""Domain workflow and provenance contract, independent of the LLM/runtime.

Validates source fields and coverage, not the truth of symbolic interpretations.
All JSON pointers below are relative to an engine's `data` object.
"""
import argparse
import json
import re

ENGINES = ('bazi', 'ziwei', 'astro')
LABELS = {'bazi': '八字', 'ziwei': '紫微', 'astro': '西方星盘'}

def schema(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required, 'additionalProperties': False}

S = {'type': 'string'}
SCALAR = {'type': ['string', 'number', 'boolean', 'null']}
CITATION = schema({'ref': S, 'path': S, 'value': SCALAR})
CONTRIBUTION = schema({'engine': {'type': 'string', 'enum': list(ENGINES)},
    'status': {'type': 'string', 'enum': ['used', 'not_relevant', 'unavailable']},
    'reason': S, 'evidence': {'type': 'array', 'maxItems': 6, 'items': CITATION}})
FINAL_SCHEMA = schema({
    'plain_summary': S, 'explanation': S,
    'actions': {'type': 'array', 'maxItems': 5, 'items': S},
    'decision_options': {'type': 'array', 'maxItems': 4, 'items': schema({
        'option': S, 'benefit': S, 'cost': S, 'risk': S, 'reversibility': S, 'first_step': S})},
    'follow_up': S, 'professional_appendix': S,
    'evidence': {'type': 'array', 'maxItems': 18, 'items': schema({
        'ref': S, 'claim': S, 'path': S, 'value': SCALAR}, ['ref', 'claim'])},
    'synthesis': {'type': 'array', 'maxItems': 3, 'items': schema({
        'theme': S, 'relationship': {'type': 'string', 'enum': ['aligned', 'mixed', 'divergent', 'insufficient']},
        'interpretation': S, 'contributions': {'type': 'array', 'minItems': 3, 'maxItems': 3, 'items': CONTRIBUTION}})},
    'caveats': {'type': 'array', 'maxItems': 5, 'items': S},
})

def workflow(message, selection=None, history=None):
    """Conservative routing hints, not a diagnosis or exhaustive safety classifier."""
    selection = selection or {}
    chart = bool(selection.get('system')) or bool(re.search(
        r'命盘|星盘|排盘|三盘|紫[微薇]|八字|运势|行运|四化|流月|流年|日课|占星|命宫|三方四正|算[一算命]|占卜|运气', message))
    decline = bool(re.search(r'(?:不要|不用|别|不需要|不想).{0,5}(?:算命|排盘|命理|占卜|三盘|八字|紫[微薇]|星盘|运势)', message))
    distress = bool(re.search(r'焦虑|担心|害怕|恐惧|心慌|崩溃|睡不着|压力|不安|恐慌', message))
    reassurance = distress and bool(re.search(r'再算|反复.{0,8}(?:算命|排盘|占卜|确认)|不停.{0,4}算|(?:保证|确认).{0,8}(?:出事|安全|没事)|一定.{0,4}没事', message))
    # A negated/quoted mention alone is not an admission of intent. The model still
    # receives the complete message; these hints are deliberately non-diagnostic.
    urgent_text=re.sub(r'(?:没有|并不|不是|不曾|不会|不打算).{0,2}(?:想自杀|要自杀|自杀|伤害自己|结束生命)', '', message)
    urgent = bool(re.search(r'(?:我|自己|朋友|家人|孩子).{0,12}(?:想自杀|要自杀|想死|不想活了|想结束生命|要伤害自己|想伤害自己)|(?:已经|刚刚).{0,5}(?:吞药|割腕)', urgent_text))
    decision = bool(re.search(r'要不要|该不该|是否应该|决策|辞职|转学|退学|换工作|投资|分手|选科|选专业|(?:感情|前任|前男友|前女友).{0,8}复合|(?:怎么选|如何选|选哪个|选择|决定).{0,12}(?:学校|工作|课程|专业|方案|职业|城市|关系)|(?:学校|工作|课程|专业|方案|职业|城市|关系).{0,12}(?:怎么选|如何选|选哪个|选择|决定)', message))
    high_stakes = bool(re.search(r'药|治疗|诊断|疾病|手术|怀孕|癌|借钱|贷款|投资|股票|基金|诉讼|法律|合同', message))
    mode = 'urgent_support' if urgent else 'decision' if decision else 'support' if distress else 'chart' if chart and not decline else 'conversation'
    needs_charts = chart and not (decline or urgent or reassurance)
    return {'mode': mode, 'needs_charts': needs_charts,
            'chart_allowed': not (decline or urgent or reassurance),
            'decision': decision and not urgent, 'support': distress or urgent,
            'reassurance_loop': reassurance, 'high_stakes': high_stakes,
            'priority': '现实情况、用户目标与可逆行动优先；命盘只提供传统象征视角，不给事件概率。',
            'limits': '路由是规则提示，不是心理诊断；需结合用户完整语境。'}

def source_kind(source, data=None):
    if source == 'memory' or source == 'user': return 'user_report_not_independently_verified'
    if source in ('forecast_registry', 'reports', 'calibration', 'omen_dictionary'):
        return 'historical_interpretation_not_fact'
    if source.startswith('history.'):
        return 'user_report_not_independently_verified' if isinstance(data, dict) and data.get('role') == 'user' else 'conversation_mixed_not_verified'
    return 'record_may_mix_user_reports_and_interpretations'

def pointer(data, path):
    if not isinstance(path, str) or not path.startswith('/') or len(path) > 400:
        raise ValueError('盘面依据path须为从data开始的JSON Pointer，例如 /pillars/day/ganzhi')
    value = data
    try:
        for raw in path[1:].split('/'):
            key = raw.replace('~1', '/').replace('~0', '~')
            if isinstance(value, list):
                if not re.fullmatch(r'0|[1-9][0-9]*', key): raise KeyError(key)
                value = value[int(key)]
            elif isinstance(value, dict): value = value[key]
            else: raise KeyError(key)
    except (IndexError, KeyError, TypeError):
        raise ValueError('盘面依据path不存在：' + path) from None
    if isinstance(value, (dict, list)): raise ValueError('请引用具体字段而非整个盘；星曜名称、宫位、角度分别给出path/value')
    return value

def check_citation(citation, evidence, engine=None):
    ref = citation.get('ref')
    if not isinstance(ref, str) or ref not in evidence: raise ValueError('引用了未读取的依据，须使用已返回的ref')
    if engine and not ref.startswith('chart:' + engine + ':'): raise ValueError('三盘依据与所属体系不匹配')
    if ref.startswith('chart:'):
        entry = evidence[ref]
        if entry.get('status') != 'ok': raise ValueError('不能引用未成功排出的盘面')
        value = pointer(entry.get('data', {}), citation.get('path'))
        if 'value' not in citation or type(value) is not type(citation['value']) and not (
            type(value) in (int, float) and type(citation['value']) in (int, float)) or value != citation.get('value'):
            raise ValueError('盘面value与实际字段不符，请逐字复制工具值：' + str(citation.get('path')))
    return ref

def _text(obj, key, limit=8000, required=False):
    val = obj.get(key)
    if not isinstance(val, str) or len(val) > limit or required and len(val.strip()) < 2:
        raise ValueError(key + '须为有效文本，不能缺少或过长')
    return val.strip()

def validate_final(args, evidence, calculated, route):
    if not isinstance(args, dict): raise ValueError('final_answer必须是结构化对象，请按工具schema补全字段')
    for key in ('plain_summary', 'explanation', 'follow_up', 'professional_appendix'):
        _text(args, key, 8000, key == 'plain_summary')
    # Keep the reading layer readable even when the model ignores section intent.
    plain=args['plain_summary']+'\n'+args['explanation']
    technical_terms=re.findall(r'日主|十神|喜用神|四柱|大运|流日|流月|流年|本命|三方四正|化禄|化权|化科|化忌|容许度|[第][一二三四五六七八九十0-9]+宫|[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]', plain)
    if len(set(technical_terms)) >= 3:
        raise ValueError('白话正文仍有密集术语/盘面推导，请将具体星曜、干支、相位及专业段落移到professional_appendix，正文只解释与现实问题的联系')
    for key, limit in (('actions', 5), ('caveats', 5)):
        rows = args.get(key)
        if not isinstance(rows, list) or len(rows) > limit or any(not isinstance(x, str) or len(x) > 1800 for x in rows):
            raise ValueError(key + '须为简短字符串数组')
    refs = args.get('evidence')
    if not isinstance(refs, list) or len(refs) > 18: raise ValueError('evidence须为最多18个依据对象')
    for row in refs:
        if not isinstance(row, dict): raise ValueError('依据须为对象')
        _text(row, 'claim', 1200, True); check_citation(row, evidence)
    options = args.get('decision_options')
    if not isinstance(options, list) or len(options) > 4: raise ValueError('decision_options须为最多4个选项')
    for opt in options:
        if not isinstance(opt, dict): raise ValueError('选项格式无效')
        for key in ('option', 'benefit', 'cost', 'risk', 'reversibility', 'first_step'): _text(opt, key, 1000, True)
    if route['decision'] and (len(options) < 2 or not args['actions'] or not args['follow_up'].strip()):
        raise ValueError('决策问题须比较至少2个可行选项（可含暂缓/低成本试行），给出行动和现实复盘标准，资料不足须条件化')
    if route['support'] and not args['actions']: raise ValueError('情绪支持须提供一个具体、低负担、可由用户选择的行动')
    reading='\n'.join([plain,args['follow_up']]+args['actions']+args['caveats'])
    if route['support'] and re.search(r'你的焦虑来自|担心的根源是|唯一真正|不想陪你|只会加深',plain):
        raise ValueError('不要替用户断定焦虑根源、宣称唯一有效方法或使用责备语气。先回应其感受，以“可能/听起来/可以先试”给可选的小行动')
    if route['support'] and route['mode']!='urgent_support' and not route.get('high_stakes') and re.search(r'(?:立刻|立即|马上).{0,20}(?:急救|急诊)|拨打.{0,6}(?:120|110)|联系.{0,8}急救|前往.{0,8}急诊',reading):
        raise ValueError('普通担心没有当下危险信息，不要套急救话术；持续影响生活时温和建议可信任的人或专业支持，给一个可控小行动')
    option_text=json.dumps(options,ensure_ascii=False)
    option_text=re.sub(r'(?:不能保证|无法保证|不能|无法|并非|不是|并不|未必|不等于|不).{0,5}(?:完全可逆|没有任何损失|零风险)','',option_text)
    if route['decision'] and re.search(r'几乎没有.{0,3}风险|风险.{0,3}几乎没有|完全可逆|没有任何损失|零风险', option_text):
        raise ValueError('选项存在未知条件，不要声称零风险/完全可逆；核实费用、退出规则和实际成本，写清条件与缺口')
    themes = args.get('synthesis')
    if not isinstance(themes, list) or len(themes) > 3: raise ValueError('synthesis须为最多3个共同议题')
    if not route['chart_allowed'] and themes: raise ValueError('本轮不排盘，请用现实支持与行动完成回答，synthesis留空')
    if route['needs_charts'] or calculated:
        if not themes: raise ValueError('已要求/计算三盘，须按共同议题逐一说明三体系的依据、分歧或缺口')
        if not args['professional_appendix'].strip(): raise ValueError('盘面解读须将专业推导单列到末尾附录')
    available = {k for ch in calculated.values() for k, v in ch.items() if v.get('status') == 'ok'}
    for theme in themes:
        if not isinstance(theme, dict): raise ValueError('三盘议题格式无效')
        _text(theme, 'theme', 300, True); _text(theme, 'interpretation', 2000, True)
        relationship = theme.get('relationship')
        if relationship not in ('aligned', 'mixed', 'divergent', 'insufficient'): raise ValueError('请标明共同点、侧重不同、分歧或不足')
        contributions = theme.get('contributions')
        if not isinstance(contributions, list) or len(contributions) != 3 or any(not isinstance(c, dict) or not isinstance(c.get('engine'), str) for c in contributions) or {c.get('engine') for c in contributions} != set(ENGINES):
            raise ValueError('每个共同议题必须恰好包含八字、紫微、西方星盘各一项，不能遗漏')
        used = 0
        for c in contributions:
            engine = c['engine']; status = c.get('status'); _text(c, 'reason', 2000, True)
            cites = c.get('evidence')
            if not isinstance(cites, list) or len(cites) > 6 or any(not isinstance(x, dict) for x in cites): raise ValueError('每体系需0至6项具体字段依据')
            if status == 'unavailable':
                if engine in available or cites: raise ValueError('已有可用排盘不能标为unavailable；不相关时标not_relevant并给已检查字段')
            elif status in ('used', 'not_relevant'):
                if engine not in available or not cites: raise ValueError('used/not_relevant须引用已读取的具体盘面字段，并说明本题如何关联或为何不相关')
                for cite in cites: check_citation(cite, evidence, engine)
                used += status == 'used'
            else: raise ValueError('三盘状态须为used/not_relevant/unavailable')
        if used < 2 and relationship != 'insufficient': raise ValueError('少于两体系相关依据时只能标insufficient，不能声称形成联动')
    if len(json.dumps(args, ensure_ascii=False)) > 32000: raise ValueError('回答过长，请聚焦核心议题')
    return args

def render_answer(args):
    """Main reading order is enforced by code; appendix is rendered separately."""
    parts = [args['plain_summary'].strip()]
    if args['explanation'].strip(): parts.append(args['explanation'].strip())
    if args['decision_options']:
        parts.append('### 可以怎样选\n\n' + '\n\n'.join(
            f"**{o['option']}**\n\n收益：{o['benefit']}\n\n投入：{o['cost']}；风险：{o['risk']}\n\n调整余地：{o['reversibility']}\n\n先做：{o['first_step']}" for o in args['decision_options']))
    if args['actions']: parts.append('### 现在可以做\n\n' + '\n'.join('- ' + s for s in args['actions']))
    if args['caveats']: parts.append('### 还需确认\n\n' + '\n'.join('- ' + s for s in args['caveats']))
    if args['follow_up'].strip(): parts.append('### 何时回看\n\n' + args['follow_up'].strip())
    return '\n\n'.join(parts)

def render_document(args):
    """Plain-text channels use the same order, with professional detail last."""
    parts = [render_answer(args)]
    relations = {'aligned':'有共同观察角度', 'mixed':'侧重不同', 'divergent':'解释存在分歧', 'insufficient':'依据不足'}
    if args['synthesis']:
        parts.append('### 三盘对照（传统象征解释）')
        for theme in args['synthesis']:
            parts.append('**' + theme['theme'] + ' · ' + relations[theme['relationship']] + '**\n\n' + theme['interpretation'])
            parts.append('\n'.join('- ' + LABELS[c['engine']] + '：' + c['reason'] for c in theme['contributions']))
    if args['professional_appendix'].strip(): parts.append('### 专业依据与方法边界\n\n' + args['professional_appendix'].strip())
    return '\n\n'.join(parts)

def validate_document(args, archive, dates, message='三盘联动报告'):
    """Recompute sources before accepting Hermes-generated structured documents."""
    from datetime import datetime
    from chart_context import bundle
    if not isinstance(args,dict):raise ValueError('回复必须是JSON对象')
    route=workflow(message)
    should_calculate=route['chart_allowed'] and (route['needs_charts'] or bool(args.get('synthesis')))
    if should_calculate and (not dates or len(set(dates)) > 7): raise ValueError('需提供1至7个实际计算日期')
    calculated = {}; evidence = {}
    for date in dict.fromkeys(dates if should_calculate else []):
        datetime.strptime(date, '%Y-%m-%d')
        charts = bundle(archive, date); calculated[date] = charts
        for engine, entry in charts.items(): evidence[f'chart:{engine}:{date}'] = entry
    # These are user-maintained records, not independently verified facts.
    for section in ('user', 'conversation_state', 'calibration'):
        if section in archive: evidence['archive:' + section] = {'source': section, 'data': archive[section]}
    validate_final(args, evidence, calculated, route)
    return render_document(args)

WORKFLOW_RULES = '''领域流程 v5：先看现实需求→检索可核实的用户陈述→需要时三盘计算→同题对照→可执行建议→专业附录。
workflow是规则提示，不是心理诊断。必须结合完整语境；不要把普通担心自动当作危机。
网站若发现初始规则遗漏了明确的当下危险，先调用prioritize_urgent_support并引用用户原话，不能因初始路由而忽略危险。反之不要把假设、否认或一般压力升级成危机。
明确自伤/自杀语境优先支持当下安全和现实求助，不用占卜判断安全。reassurance_loop时温和承接担心，不重新排盘或许诺绝对安全，转向一个可控小行动。
决策以用户目标、已知现实、时间/预算/支持等约束为先；缺少关键事实时说明条件，只问最有帮助的一两点。比较至少两个选项的收益、成本、风险和可逆性，纳入暂缓或低成本试行，给现实复盘指标。医疗、财务、法律问题不凭盘面作决定，必要时建议有资质的专业帮助。不得编造事实/精确概率。
三盘不是三票投票，不计算统一吉凶分或事件概率。按同一现实议题组织synthesis，八字/紫微/西方星盘各填一项：used、not_relevant或unavailable，注明共同点/不同侧重/分歧/不足。不要为了凑三盘而硬说相同。available的体系即使not_relevant也须列实际检查过的字段和具体原因。
所有chart引用须含ref、path（相对data的JSON Pointer，如 /pillars/day/ganzhi、/palaces/0/major/0/name）、value（原始标量值；数字不能改成字符串）。字段校验只保证来源，不证明解释成立；象征推论须用“可作为…的观察角度”等条件措辞。
final_answer按结构提交：plain_summary是直接可懂的回答，explanation用日常语言连接已知现实与建议；actions给1至3个低负担动作；非决策decision_options=[]；follow_up给现实观察点或留空；专业术语与推导只放professional_appendix；evidence为真正读过的依据；synthesis为同题三盘对照；caveats仅列实际缺口。正文不要重复专业附录，不以一串星曜/十神开头。
白话摘要和explanation不要逐盘罗列干支/星曜/相位；具体专业段落全部移到professional_appendix。课程仅给时长不等于费用低、试听免费或随时可退出；选项的成本/风险/可逆性需明示未知条件，不能用“完全可逆/没有任何损失/零风险”。普通焦虑不要自动添加急救或自伤警告，只有实际危险语境才采用相应支持；本轮没有排盘是回答策略，不要假称用户要求不排盘。
支持性回应先承接用户表达的感受，不以“这次我不再给你算/不想陪你”打头；说明选择时简短温和。不把焦虑根源归结为没准备好，不说“只会更慌/唯一有效方法”，不对效果作保证。用“听起来…很难受；可以先选一个小步骤看看是否有帮助”这样的可选择表达。行动不以完成学习任务作为获得支持的条件。
历史预测、旧报告和先前助手结论不能当用户事实；不将模型建议自动存入长期记忆。不知道就说明缺口，不编造用户经历。避免“注定/必有灾祸/保证转运”和靠反复占卜消除不确定性。
总工具循环8轮。引用失败可修复再提交；不得跳过验证。'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='输出网站与Hermes共享的领域流程规则与结构契约')
    parser.add_argument('--message', default='今日三盘联动晨报')
    parser.add_argument('--validate', help='校验结构化JSON并输出白话在前、专业在后的全文')
    parser.add_argument('--dates', help='逗号分隔的已分析日期，最多7个')
    parser.add_argument('--archive', default=None)
    args = parser.parse_args()
    if args.validate:
        import os
        from pathlib import Path
        from context_engine import choose_date
        document = json.loads(Path(args.validate).read_text(encoding='utf-8'))
        archive = json.loads(Path(args.archive or os.path.expanduser('~/.hermes/zhiming/archive.json')).read_text(encoding='utf-8'))
        print(validate_document(document, archive, args.dates.split(',') if args.dates else [choose_date(args.message)], args.message))
    else:
        print(json.dumps({'version': '5.0', 'workflow': workflow(args.message), 'rules': WORKFLOW_RULES,
                          'final_schema': FINAL_SCHEMA}, ensure_ascii=False, indent=2))
