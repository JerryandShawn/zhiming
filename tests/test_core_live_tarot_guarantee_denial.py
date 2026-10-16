"""The original synthetic live Tarot outputs through real PG/LangGraph.

Only the model port is replaced. Original prose is intact; opaque citations
are rebound by an exact rule/text/feature match to the current actual draw.
"""
from copy import deepcopy
import hashlib
import json
import unittest
import uuid
from psycopg import sql
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn
from tools.compare_core_providers import card_projection

SYMBOLIC='象征解释被提升为现实确定性或概率'
LIMIT='真正能否撤回，取决于已核实的费用、期限、材料依赖和退出条件，不能由牌面保证'
CARDS=[{'card_id':'major-00','orientation':'upright'},
       {'card_id':'major-01','orientation':'reversed'},
       {'card_id':'major-14','orientation':'upright'}]
ORIGINAL=json.loads(r'''
{
  "inspection_sha256": "021ad0c85dbcc64bb849d75a684d80f45bbdfd0488e6f2a2172f726f227b9202",
  "observed_commit": "890c32ea3e645981b539060088135d375fe19bb1",
  "original_claim": {
    "branch_id": "draw-85ecf015ae7cc230a5ec136c",
    "claim_id": "claim-6e868e02bdbbdb1f5271cd5a0582e569",
    "claim_type": "symbolic_reflection",
    "counter_factors": [
      "不是鼓励无视代价，也不是预告某次冒险必成。",
      "拥有资源不等于已经具备全部条件。",
      "折中不等于忽略底线或对所有人退让。"
    ],
    "derivation_summary": "已逐项核对本轮授权产物字段、规则前提与解释范围；此说明不包含隐藏思维链。",
    "editorial_status": "original_editorial_unreviewed",
    "empirical_status": "reflection_not_prediction",
    "feature_refs": [
      {
        "artifact_id": "tarot-b8768973eeb9db4a46f5983d",
        "feature_key": "cards",
        "path": "/data/cards",
        "value": [
          {
            "card_id": "major-00",
            "name": "愚人",
            "orientation": "upright",
            "position": 1
          },
          {
            "card_id": "major-01",
            "name": "魔术师",
            "orientation": "reversed",
            "position": 2
          },
          {
            "card_id": "major-14",
            "name": "节制",
            "orientation": "upright",
            "position": 3
          }
        ]
      },
      {
        "artifact_id": "tarot-b8768973eeb9db4a46f5983d",
        "feature_key": "spread_id",
        "path": "/data/spread_id",
        "value": "reflect3"
      },
      {
        "artifact_id": "tarot-b8768973eeb9db4a46f5983d",
        "feature_key": "deck_version",
        "path": "/data/deck_version",
        "value": "zhiming-geometric-78-v1"
      },
      {
        "artifact_id": "tarot-b8768973eeb9db4a46f5983d",
        "feature_key": "status",
        "path": "/data/status",
        "value": "finalized"
      }
    ],
    "interpretation_id": "card_reflection",
    "limitations": [
      "产品牌阵是反思设计，不宣称唯一传统格式。",
      "编辑资产未获外部专家认证，也不是预测模型。"
    ],
    "owner_user_id": "release_acceptance_b8d8e3c7b04f43629e56e5bb0137fabb",
    "pack_version": "core-knowledge-2026-10-11-v2",
    "real_world_link_status": "not_established",
    "revision": 43,
    "rule_hash": "f773602e082e3897f6358d98fb3cbf273e3ae8aaaea4956f28a4eb4ecf63729a",
    "rule_id": "tarot.editorial.complete-deck.v1",
    "rule_version": "1.0.0",
    "school_id": "zhiming-editorial-v1",
    "scope": "同一轮已保存问题与牌阵的象征反思；不产生新现实事实",
    "source_refs": [
      "zhiming-tarot-editorial-v1"
    ],
    "subject_id": "self",
    "system": "tarot",
    "text": "第1牌位 愚人（正位）：保留好奇，用小实验探索尚不熟悉的道路。；第2牌位 魔术师（逆位）：可能高估掌控力，或有工具却缺少明确目标。；第3牌位 节制（正位）：通过试验比例和节奏，让不同需求逐渐协调。。这些是明镜原创编辑反思角度，牌位提供问题视角，不能证明现实情况。实际选择须另核对已确认目标、约束与代价。",
    "time_scale": "question"
  },
  "original_question": "请解读这次固定牌阵。问题：虚构练习中，怎样整理一个可撤回的学习步骤？。补充背景：仅作虚构学习练习的反思，不作现实预测；无需出生资料。",
  "outputs": {
    "intake": {
      "attachment_observations": [],
      "plan": {
        "decision": false,
        "missing_inputs": [
          "本次固定牌阵的具体牌面信息（各牌所在位置、牌名及正逆位）"
        ],
        "mode": "tarot",
        "rationale": "用户请求以塔罗固定牌阵进行学习主题的虚构反思，并明确不作现实预测、无需出生资料。当前未提供牌阵的牌面信息，无法完成对应解读。",
        "systems": [
          "tarot"
        ],
        "target_date": "2026-10-16",
        "time_scale": "natal",
        "topic": "study"
      },
      "proposals": [],
      "retire_fact_ids": []
    },
    "repair": {
      "actions": [
        "写下一个虚构学习主题、本次试学假设和“完成/未完成”的判断标准。",
        "列明撤回条件，例如时间上限、预算上限、材料来源不明、影响休息或无法退出时即暂停。",
        "只准备最低限度工具，把费用、期限和退出规则标为待核实，不一次性囤齐资源。",
        "进行一个低投入试学单元，记录实际耗时、阻碍、收获和是否触发停止条件。",
        "复盘时选择继续、缩小范围、调整节奏或撤回，并写下下一步的停止点。"
      ],
      "caveats": [
        "牌阵只提供象征反思，不证明现实能力、学习结果或方案必然可撤回。",
        "实际可撤回性取决于费用、期限、材料依赖、退出规则和机会成本；这些均未提供，需核实。",
        "魔术师逆位只提示“高估掌控或目标不清”的可能视角，不是对个人能力或资源状况的诊断。",
        "本轮引用的编辑声明未获外部专家认证，也不是预测模型。",
        "暂缓核实也有时间与机会成本，不应被视为完全无代价。"
      ],
      "cited_claim_ids": [
        "claim-6e868e02bdbbdb1f5271cd5a0582e569"
      ],
      "cited_fact_ids": [],
      "decision_options": [],
      "explanation": "本轮目标不是预测学习结果，而是把“可撤回”落实为一个现实可检查的步骤设计。当前缺少实际学习主题、可用时间、预算、期限、资料依赖和退出规则，因此不能推断任何方案完全可逆或无损失。\n\n象征上，愚人正位支持从好奇的小实验开始；魔术师逆位提醒先澄清目标与工具，避免以为有资源就已有掌控力；节制正位提示用小比例投入、记录反馈并逐步调整。落到现实，可把步骤整理为五步：一是写出一个具体主题和试学假设；二是明确完成标准、时间上限和停止条件；三是只准备最低限度工具，并把费用与退出规则标为待核实；四是运行一个短而可暂停的试学单元；五是在复盘点决定继续、缩小、调整或撤回。\n\n这里的主要代价是时间、精力和机会成本；即使先核实再开始，也会付出等待成本。真正能否撤回，取决于已核实的费用、期限、材料依赖和退出条件，不能由牌面保证。",
      "follow_up": "完成首个低投入试学单元后立即复盘；若尚未开始，可在一周后检查费用、期限、退出规则和停止条件是否已核实。",
      "plain_summary": "这次三牌反思可整理为“低承诺试学—核对目标与工具—小比例投入—按期复盘并可停止”。先写下一个具体主题、试学假设、完成标准和撤回条件，再只用最低限度工具进行短试验，最后依据记录决定继续、调整或撤回。牌面仅提供反思视角，不能证明你已经准备好、必然学成或步骤一定可撤回；费用、期限与退出条件均需另行核实。",
      "professional_appendix": "本轮引用的声明为 claim-6e868e02bdbbdb1f5271cd5a0582e569，规则 tarot.editorial.complete-deck.v1，牌阵 reflect3，牌组版本 zhiming-geometric-78-v1，claim_type 为 symbolic_reflection，time_scale 为 question。声明的 empirical_status 是 reflection_not_prediction，real_world_link_status 是 not_established，editorial_status 是 original_editorial_unreviewed；因此只能作为同一轮问题的象征反思，不能证明现实能力、结果、因果或可撤回性。\n\n牌位一：愚人正位。声明给出的视角是“保留好奇，用小实验探索尚不熟悉的道路”。对应到练习，可表现为先设计一个低承诺试学单元，而非立即承诺长期路线。其反例边界是：这不是鼓励无视代价，也不是预告冒险必成。\n\n牌位二：魔术师逆位。声明给出的视角是“可能高估掌控力，或有工具却缺少明确目标”。对应到步骤整理，应先区分目标、资源、方法和验证标准，再决定工具是否必要；但该牌位不能据此断言个人确实能力不足或资源缺乏。\n\n牌位三：节制正位。声明给出的视角是“通过试验比例和节奏，让不同需求逐渐协调”。对应到执行，可采用“小量尝试—记录反馈—调整配比—再次试学”的节奏，同时保留预算、休息、材料来源和退出条件方面的底线。其反例边界是：折中不等于忽略底线或对所有要求退让。\n\n缺失与张力：实际学习主题、可用时间、费用、期限、退出规则、资料依赖和个人熟悉程度均未提供，故不能判断现实可撤回程度。三张牌之间可形成一个连贯的反思框架——开始要小、目标要清、投入要有节奏——但该框架不是预测，也不能替代现实核实。"
    },
    "specialist:tarot": {
      "claim_ids": [
        "claim-6e868e02bdbbdb1f5271cd5a0582e569"
      ],
      "discussion": "本轮引用的是一个三牌位反思声明，规则为 tarot.editorial.complete-deck.v1，牌阵 reflect3，牌组版本 zhiming-geometric-78-v1；其 claim_type 是 symbolic_reflection，因此只提供象征视角，不证明学习状态、成败或现实因果。声明也标注 real_world_link_status 为 not_established，故不能据此断定你已经准备好、会学成，或某方案必然可撤回。\n\n第1牌位愚人正位提示：把“整理学习步骤”的起点放在好奇与小实验，而不是一次性承诺长期路线。可反思的设计是：先选一个具体主题，写清本次试学假设、最低材料、预定停止点与回看日期；第一步应当小到能暂停、恢复原状，并保留选择其他路线的空间。这里不能反推出“冒险没有代价”：声明的反例明确说明，这不是鼓励无视代价，也不预告冒险必成。\n\n第2牌位魔术师逆位提示：可能存在“工具很多、掌控感过强、目标却不够清楚”的风险。整理步骤时，先区分目标、资源、方法和验证标准，再决定哪些工具真正必要；例如学习材料不必一次收齐，练习产出也不必追求展示效果。此牌位只能提示高估掌控力的可能性，不能据此断言你确实能力不足或一定缺乏资源。相应检查点是：目标是否可表述、退出条件是否写明、时间安排是否受其他任务挤压，以及工具成本是否待核实。\n\n第3牌位节制正位提示：用比例和节奏协调需求。较稳妥的象征性框架是“小量尝试—记录反馈—调整配比—再次试学”，同时保留一条底线：遇到超出预算、影响休息、材料来源不明或退出条件不清时暂停，而不是为了折中而无限退让。声明的反例也指出，折中不等于忽略底线。\n\n综合三张牌，这个虚构练习可整理为：先设一个低承诺试学单元；再核对目标与工具是否匹配；随后以小比例投入并设置复盘和撤回点。撤回是否真正可行，仍取决于实际费用、期限、资料依赖和机会成本；这些均不能由牌面推断。",
      "system": "tarot",
      "uncertainties": [
        "学习目标、可用时间、费用、退出条件与期限均未提供，需另行核实。",
        "牌阵只提供同一轮问题的象征反思，不能证明现实能力、结果或可撤回性。",
        "第2牌位的“高估掌控力或缺少明确目标”是可能视角，不是对个人状况的诊断。",
        "声明编辑状态为 original_editorial_unreviewed，未获外部专家认证，也不是预测模型。"
      ]
    },
    "synthesis": {
      "actions": [
        "写下一个虚构学习主题、本次试学假设和“完成/未完成”的判断标准。",
        "列明撤回条件，例如时间上限、预算上限、材料来源不明、影响休息或无法退出时即暂停。",
        "只准备最低限度工具，把费用、期限和退出规则标为待核实，不一次性囤齐资源。",
        "进行一个低投入试学单元，记录实际耗时、阻碍、收获和是否触发停止条件。",
        "复盘时选择继续、缩小范围、调整节奏或撤回，并写下下一步的停止点。"
      ],
      "caveats": [
        "牌阵只提供象征反思，不证明现实能力、学习结果或方案必然可撤回。",
        "实际可撤回性取决于费用、期限、材料依赖、退出规则和机会成本；这些均未提供，需核实。",
        "魔术师逆位只提示“高估掌控或目标不清”的可能视角，不是对个人能力或资源状况的诊断。",
        "本轮引用的编辑声明未获外部专家认证，也不是预测模型。",
        "暂缓核实也有时间与机会成本，不应被视为完全无代价。"
      ],
      "cited_claim_ids": [
        "claim-6e868e02bdbbdb1f5271cd5a0582e569"
      ],
      "cited_fact_ids": [],
      "decision_options": [
        {
          "benefit": "投入较小，能较快获得真实反馈，并保留暂停或改路线的空间。",
          "cost": "仍会消耗时间和精力，也可能产生少量材料或工具成本。",
          "first_step": "写下试学主题、假设、完成标准、时间上限和撤回条件。",
          "option": "先运行一个低承诺试学单元",
          "reversibility": "原则上较易停止，但只有在费用、期限和退出条件核实后才能确认可撤回程度。",
          "risk": "可能低估资料依赖或工具成本；小试验也不保证有效。"
        },
        {
          "benefit": "能在投入前澄清费用、期限、资料来源和退出规则，减少不可逆投入。",
          "cost": "会推迟开始，并产生等待和机会成本。",
          "first_step": "列出必须核实的问题：总费用、退款或退出规则、所需时间、资料依赖和停止条件。",
          "option": "先核实条件再开始学习",
          "reversibility": "尚未投入时通常较容易改变计划，但询问与等待本身并非零成本。",
          "risk": "可能因信息不完整而无限等待，或把核实变成拖延。"
        }
      ],
      "explanation": "本轮目标不是预测学习结果，而是把“可撤回”落实为一个现实可检查的步骤设计。当前缺少实际学习主题、可用时间、预算、期限、资料依赖和退出规则，因此不能推断任何方案完全可逆或无损失。\n\n象征上，愚人正位支持从好奇的小实验开始；魔术师逆位提醒先澄清目标与工具，避免以为有资源就已有掌控力；节制正位提示用小比例投入、记录反馈并逐步调整。落到现实，可把步骤整理为五步：一是写出一个具体主题和试学假设；二是明确完成标准、时间上限和停止条件；三是只准备最低限度工具，并把费用与退出规则标为待核实；四是运行一个短而可暂停的试学单元；五是在复盘点决定继续、缩小、调整或撤回。\n\n这里的主要代价是时间、精力和机会成本；即使先核实再开始，也会付出等待成本。真正能否撤回，取决于已核实的费用、期限、材料依赖和退出条件，不能由牌面保证。",
      "follow_up": "完成首个低投入试学单元后立即复盘；若尚未开始，可在一周后检查费用、期限、退出规则和停止条件是否已核实。",
      "plain_summary": "这次三牌反思可整理为“低承诺试学—核对目标与工具—小比例投入—按期复盘并可停止”。先写下一个具体主题、试学假设、完成标准和撤回条件，再只用最低限度工具进行短试验，最后依据记录决定继续、调整或撤回。牌面仅提供反思视角，不能证明你已经准备好、必然学成或步骤一定可撤回；费用、期限与退出条件均需另行核实。",
      "professional_appendix": "本轮引用的声明为 claim-6e868e02bdbbdb1f5271cd5a0582e569，规则 tarot.editorial.complete-deck.v1，牌阵 reflect3，牌组版本 zhiming-geometric-78-v1，claim_type 为 symbolic_reflection，time_scale 为 question。声明的 empirical_status 是 reflection_not_prediction，real_world_link_status 是 not_established，editorial_status 是 original_editorial_unreviewed；因此只能作为同一轮问题的象征反思，不能证明现实能力、结果、因果或可撤回性。\n\n牌位一：愚人正位。声明给出的视角是“保留好奇，用小实验探索尚不熟悉的道路”。对应到练习，可表现为先设计一个低承诺试学单元，而非立即承诺长期路线。其反例边界是：这不是鼓励无视代价，也不是预告冒险必成。\n\n牌位二：魔术师逆位。声明给出的视角是“可能高估掌控力，或有工具却缺少明确目标”。对应到步骤整理，应先区分目标、资源、方法和验证标准，再决定工具是否必要；但该牌位不能据此断言个人确实能力不足或资源缺乏。\n\n牌位三：节制正位。声明给出的视角是“通过试验比例和节奏，让不同需求逐渐协调”。对应到执行，可采用“小量尝试—记录反馈—调整配比—再次试学”的节奏，同时保留预算、休息、材料来源和退出条件方面的底线。其反例边界是：折中不等于忽略底线或对所有要求退让。\n\n缺失与张力：实际学习主题、可用时间、费用、期限、退出规则、资料依赖和个人熟悉程度均未提供，故不能判断现实可撤回程度。三张牌之间可形成一个连贯的反思框架——开始要小、目标要清、投入要有节奏——但该框架不是预测，也不能替代现实核实。"
    }
  },
  "snapshot_fact_ids": [],
  "synthetic_only": true
}
''')


def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


class RecordedLiveModel:
    def __init__(self,final_phase='synthesis',patch=None,invalid=None,force_repair=False):
        self.final_phase=final_phase;self.patch=patch;self.invalid=invalid
        self.force_repair=force_repair
        self.calls=[];self.mapping={};self.outputs={}
    def bind(self,value):
        if isinstance(value,dict):return {k:self.bind(v) for k,v in value.items()}
        if isinstance(value,list):return [self.bind(v) for v in value]
        if isinstance(value,str):
            for old,new in self.mapping.items():value=value.replace(old,new)
        return value
    def generate(self,**kwargs):
        purpose=kwargs['purpose'];self.calls.append(purpose)
        data=kwargs['payload']['reference_data']
        assert data.get('facts',[])==[],'No private or synthetic profile facts belong to this reading'
        if purpose!='intake':
            old=ORIGINAL['original_claim']
            matches=[c for c in data['claims'] if all(c[k]==old[k] for k in ('system','rule_id','school_id','text','time_scale'))
                and [(f['path'],f['value']) for f in c['feature_refs']]==[(f['path'],f['value']) for f in old['feature_refs']]]
            assert len(matches)==1,'One exact current rule/text/feature match is required'
            self.mapping[old['claim_id']]=matches[0]['claim_id']
            for before,after in zip(old['feature_refs'],matches[0]['feature_refs']):
                self.mapping[before['artifact_id']]=after['artifact_id']
        key=self.final_phase if purpose=='synthesis' else purpose
        output=self.bind(deepcopy(ORIGINAL['outputs'][key]))
        if purpose in ('synthesis','repair'):
            if purpose=='synthesis' and self.force_repair:output['plain_summary']+='牌面保证现实成功。'
            if self.patch is not None:output.update(deepcopy(self.patch))
            if self.invalid is not None:
                output['cited_'+self.invalid+'_ids'].append('invented-synthetic-reference')
        self.outputs[purpose]=deepcopy(output)
        return {'output':output,'usage':{'input_tokens':1,'output_tokens':1},'model':'recorded-live-synthetic-tarot'}


class ObservedService(ConsultationService):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.validation_attempts=[]
    def _validate(self,owner,run,final):
        issues=super()._validate(owner,run,final);self.validation_attempts.append(list(issues));return issues


class LiveTarotDenialPostgresTests(unittest.TestCase):
    def setUp(self):
        self.schema='test_live_denial_'+uuid.uuid4().hex[:16]
        self.repo=PostgresRepository(test_dsn(),schema=self.schema,max_size=3)
        self.addCleanup(self.cleanup)
        self.owner='synthetic-live-denial';self.repo.ensure_owner(self.owner)
        self.service=ObservedService(self.repo)
        source=self.service.memory.receive(self.owner,content='虚构验收：整理学习任务。目标：用一个可撤回的小练习整理学习顺序',source_id='fixed-case-original')
        self.case=self.service.memory.create_case(self.owner,'self','虚构验收：整理学习任务',
            goal='用一个可撤回的小练习整理学习顺序',message_id=source['id'])['id']
        self.draw=self.service.tarot.create_draw(self.owner,subject_id='self',case_id=self.case,
            question='虚构练习中，怎样整理一个可撤回的学习步骤？',spread_id='reflect3',draw_source='manual',
            reversals=True,manual_cards=CARDS,idempotency_key='fixed-live-manual')['draw']
        self.draw=self.service.tarot.reveal(self.owner,self.draw['id'])
    def cleanup(self):
        with self.repo.connection() as c:runs=c.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch']+1):self.service.runtime.purge(run['id'],epoch)
        with self.repo.connection() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()
    def execute(self,final_phase='synthesis',patch=None,invalid=None,expected_issue=None,force_repair=False):
        model=RecordedLiveModel(final_phase,patch,invalid,force_repair);self.service.model=model
        start=len(self.service.validation_attempts)
        run=self.service.submit(owner=self.owner,message=ORIGINAL['original_question'],mode='tarot',
            request_id='reading:'+uuid.uuid4().hex,case_ids=[self.case],depth='standard',draw_id=self.draw['id'])
        if expected_issue:
            with self.assertRaises(InvalidAnswer) as caught:self.service.execute(self.owner,run['id'])
            self.assertEqual(caught.exception.code,'REFERENCE_ERROR')
            current=self.repo.fetch_run(self.owner,run['id'])
            self.assertEqual((current['status'],current['calls'],current['repair_used']),('failed',4,True))
            self.assertIsNone(current['result'])
            self.assertEqual(self.service.validation_attempts[start:],[[expected_issue],[expected_issue]])
        else:
            result=self.service.execute(self.owner,run['id']);current=self.repo.fetch_run(self.owner,run['id'])
            self.assertEqual((current['status'],current['calls'],current['call_limit'],current['repair_used']),
                ('succeeded',4 if force_repair else 3,6,force_repair))
            self.assertEqual(self.service.validation_attempts[start:],[[SYMBOLIC],[]] if force_repair else [[]])
            self.assertEqual(model.calls,['intake','specialist:tarot','synthesis']+(['repair'] if force_repair else []))
            final=model.outputs['repair' if force_repair else 'synthesis']
            self.assertEqual(self.service._record(self.owner,run['id'],'validation')['final'],final)
            for key,value in final.items():
                if key=='professional_appendix':self.assertTrue(result[key].startswith(value+'\n\n**tarot'))
                else:self.assertEqual(result[key],value)
            calls=len(model.calls);self.assertEqual(self.service.execute(self.owner,run['id']),result)
            self.assertEqual(len(model.calls),calls)
        self.assertEqual(self.service._record(self.owner,run['id'],'snapshot')['fact_ids'],[])
        self.assertEqual(self.service.memory.facts(self.owner),[])
        self.assertEqual(card_projection(self.service.tarot.get(self.owner,self.draw['id'])),CARDS)
        self.assertEqual(current['calls'],len(model.calls))
        return model
    def test_complete_original_synthesis_commits_and_replays_without_changing_draw(self):
        self.assertTrue(ORIGINAL['synthetic_only']);self.assertEqual(ORIGINAL['snapshot_fact_ids'],[])
        self.assertEqual(ORIGINAL['inspection_sha256'],'021ad0c85dbcc64bb849d75a684d80f45bbdfd0488e6f2a2172f726f227b9202')
        self.assertEqual(digest(ORIGINAL['outputs']['synthesis']),'9054fadf95572d062b45a1e4aa78aef9419aa7cd2825cf7bcbe754196bb6892c')
        before=digest(ORIGINAL);model=self.execute()
        self.assertEqual(model.outputs['synthesis'],model.bind(ORIGINAL['outputs']['synthesis']))
        self.assertEqual(digest(ORIGINAL),before)
    def test_complete_original_repair_also_validates_without_prose_edits(self):
        self.assertEqual(digest(ORIGINAL['outputs']['repair']),'fa943e0add27f356262aa994c9dc16bee815f149c49c18505670a6ea2f307087')
        before=digest(ORIGINAL);model=self.execute(final_phase='repair')
        self.assertEqual(model.outputs['synthesis'],model.bind(ORIGINAL['outputs']['repair']))
        self.assertEqual(digest(ORIGINAL),before)
    def test_one_global_repair_keeps_the_complete_original_repair_and_fixed_cards(self):
        model=self.execute(force_repair=True)
        self.assertEqual(model.outputs['repair'],model.bind(ORIGINAL['outputs']['repair']))
    def test_assertions_double_denials_quotes_and_renewed_claims_remain_rejected(self):
        variants=['真正能否撤回，牌面保证','真正能否撤回，不是不能由牌面保证',
            '真正能否撤回，并非不能由牌面保证','真正能否撤回，“不能由牌面保证”',
            '“真正能否撤回，不能由牌面保证”','真正能否撤回，不能由牌面保证，但牌面保证结果',
            '真正能否撤回，不能由牌面保证，但保证结果','真正能否撤回，不能由牌面保证你必然成功']
        for value in variants:
            with self.subTest(value=value):
                explanation=ORIGINAL['outputs']['synthesis']['explanation'].replace(LIMIT,value)
                self.execute(patch={'explanation':explanation},expected_issue=SYMBOLIC)
    def test_real_limit_cannot_excuse_an_assertion_in_another_field(self):
        self.execute(patch={'plain_summary':'牌面保证现实成功。'},expected_issue=SYMBOLIC)
    def test_original_output_does_not_excuse_invalid_fact_or_claim_references(self):
        for kind,issue in [('fact','引用了本轮有效范围之外的事实'),('claim','引用了未通过规则核验的声明')]:
            with self.subTest(kind=kind):self.execute(invalid=kind,expected_issue=issue)

    def test_symbolic_evidence_denial_before_subject_commits_with_original_cards(self):
        for suffix in ('', '，也不能给出成败概率'):
            with self.subTest(suffix=suffix):
                self.execute(patch={'explanation':'本轮仅作象征反思，因此不能把牌面当作结果、对方态度或顺利程度的证明'+suffix+'。'})

    def test_symbolic_evidence_denial_does_not_excuse_guarantees_or_quotes(self):
        limit='不能把牌面当作结果、对方态度或顺利程度的证明'
        variants=['牌面当作结果、对方态度或顺利程度的证明',
            '不是'+limit,'并非'+limit,'不能说'+limit,
            '“'+limit+'”','“此前的说法。'+limit+'”',
            limit+'，但牌面保证结果',limit+'，但保证结果',
            limit+'，也不能给出成败概率，但保证结果',
            limit+'且保证结果',limit+'，所以现实一定成功']
        for value in variants:
            with self.subTest(value=value):
                self.execute(patch={'explanation':value+'。'},expected_issue=SYMBOLIC)


if __name__=='__main__':unittest.main()
