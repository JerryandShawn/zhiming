"""Tarot-specific contract on the same ChatAgent, not a second chatbot."""
import copy,re
from guidance import FINAL_SCHEMA,schema,S

TAROT_SCHEMA=copy.deepcopy(FINAL_SCHEMA)
TAROT_SCHEMA['properties'].update({
    'reality_context':{'type':'array','maxItems':10,'items':schema({'kind':{'type':'string','enum':['known','preference','assumption','missing']},'statement':S,'ref':S})},
    'card_interpretations':{'type':'array','maxItems':5,'items':schema({'position':{'type':'integer'},'card_id':S,'orientation':{'type':'string','enum':['upright','reversed']},'theme':S,'interpretation':S,'question':S})},
    'tarot_synthesis':{'type':'array','maxItems':4,'items':S},
})
TAROT_SCHEMA['required']+=['reality_context','card_interpretations','tarot_synthesis']

def normalize_final(args):
    args=dict(args)
    for key in ('explanation','follow_up','professional_appendix'):args.setdefault(key,'')
    for key in ('actions','decision_options','evidence','synthesis','caveats'):args.setdefault(key,[])
    return args

def validate_tarot(args,draw,evidence,full=True):
    cards=args.get('card_interpretations',[])
    if not isinstance(cards,list) or (full and len(cards)!=len(draw['cards'])):raise ValueError('塔罗解读必须逐个解释真实牌位；不能漏牌或增牌')
    expected={c['position']:c for c in draw['cards']};seen=set()
    for c in cards:
        if not isinstance(c,dict) or not isinstance(c.get('position'),int):raise ValueError('牌位格式无效')
        pos=c['position'];real=expected.get(pos)
        if not real or pos in seen or c.get('card_id')!=real['card_id'] or c.get('orientation')!=real['orientation']:
            raise ValueError('牌位/牌名/方向与已冻结抽牌不符，重新生成解释不能换牌')
        seen.add(pos)
        for key in ('theme','interpretation','question'):
            if not isinstance(c.get(key),str) or not c[key].strip() or len(c[key])>2500:raise ValueError('每张牌需具体主题、结合问题的解释及反思问题')
    context=args.get('reality_context',[])
    if not isinstance(context,list):raise ValueError('现实背景须区分已知/偏好/假设/缺口')
    for row in context:
        if not isinstance(row,dict) or row.get('kind') not in ('known','preference','assumption','missing'):raise ValueError('现实背景类型无效')
        if row['kind'] in ('known','preference'):
            ref=row.get('ref');entry=evidence.get(ref)
            if not entry:raise ValueError('已知现实须引用本轮已授权的用户陈述；牌意不能当事实')
            if ref.startswith(('tarot:','draw:','chart:')):raise ValueError('随机牌面或传统解释不构成已知现实来源')
    if not isinstance(args.get('tarot_synthesis',[]),list) or any(not isinstance(x,str) for x in args.get('tarot_synthesis',[])):raise ValueError('牌间关系须为简短文字列表')
    if full:
        from tarot_deck import card
        plain=args.get('plain_summary','')+'\n'+args.get('explanation','')
        names={card(c['card_id'])['name'] for c in draw['cards']}
        if sum(name in plain for name in names)>=2:raise ValueError('白话正文不要逐牌罗列牌名/正逆位推导；放入card_interpretations、tarot_synthesis或末尾professional_appendix，正文解释现实选择')
    text=str(args)
    if re.search(r'(?:成功率|中奖率|发财概率).{0,8}\d+\s*%',text):raise ValueError('牌面不能换算现实事件概率')
    return True

TAROT_RULES='''本轮使用同一事项与记忆的塔罗视角，不要求出生信息，不默认计算三盘。抽牌已由程序完成并冻结，模型无权改牌、换方向或重抽。
按实际 card_id、orientation、position 逐牌解释；themes来源是本产品编辑性象征内容，不是用户事实。没有图片视觉输入时不要描述图上人物/物件细节。
reality_context区分known/preference/assumption/missing；已知现实引用当前question_ref、补充事实消息ref或有效记忆ref。由牌意引出的新因素只能写待核查。
card_interpretations每张写传统主题、与本问题的条件性联系和一个可思考问题；tarot_synthesis保留张力/无关/未知。不要因牌好或正位多推荐选项。
选择题现实比较保留A/B冻结含义，可包含暂缓或其他现实选项；事实不足可明确暂不推荐。白话正文先说现实可做的事，牌意和方法细节放末尾。牌意不能存为用户事实。
plain_summary和explanation不能逐牌串起牌名/正逆位来当理由；全部逐牌推导放card_interpretations和tarot_synthesis。不因留在现岗位就断言熟悉流程、已有支持或协商成本低；未提供的条件写missing或assumption，倾向必须仅依已有现实信息支持。
再生成只产生新的解释版本，不改变draw。普通“第三张是什么意思”可只解释第三张；不把上次建议当用户已执行。反馈写事项事件须依据用户原话，不自动提醒。
引用结构校验不证明解释成立。语义支持需复核，资料不足保留不确定性。'''
