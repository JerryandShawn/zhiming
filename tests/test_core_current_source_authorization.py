"""Real PG/Core/LangGraph authorization tests; only model responses are replaced."""
from copy import deepcopy
from contextlib import closing
import asyncio
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from psycopg import sql
from pydantic import ValidationError

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.memory import explicit_save_authorization, fact_kind, FACT_KINDS, CATEGORIES
from mingjing_core.adapters.channels.hermes import HermesChannelAdapter
from mingjing_core.adapters.feishu_gateway import FeishuGateway
from mingjing_core.domain.contracts import EvidenceError, ScopeError, SourcePolicy
from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn
from tests.test_core_pg_channels import FixtureModel


BACKGROUND = 'A班次尚未确认，B明确白班但费用未知'
DECLARATION = '请用这组已经记录的实体塔罗牌（按顺序：major-00 upright；cups-01 reversed；pentacles-08 upright）'
MESSAGE = BACKGROUND + '。' + DECLARATION + '。'


class SourceProvider(FixtureModel):
    def __init__(self):
        super().__init__()
        self.proposals = []
        self.tarot = False
        self.unknown_citation = False

    def generate(self, **kwargs):
        response = super().generate(**kwargs)
        if kwargs['purpose'] == 'intake':
            response['output']['plan'].update(mode='tarot' if self.tarot else 'conversation',
                systems=['tarot'] if self.tarot else [], decision=False)
            response['output']['proposals'] = deepcopy(self.proposals)
        elif not kwargs['purpose'].startswith('specialist:'):
            if self.unknown_citation:
                response['output']['cited_fact_ids'].append('fact_not_in_current_scope')
        return response


class AuthorizationSyntax(unittest.TestCase):
    def test_shared_category_mapping_preserves_known_kinds_and_rejects_unknown(self):
        for category,kind in CATEGORIES.items():
            self.assertEqual(fact_kind(category=category),kind)
        for kind in FACT_KINDS:
            self.assertEqual(fact_kind(category=kind),kind)
        for invalid in ('not-a-kind','Background','',True,{},[]):
            with self.subTest(category=invalid),self.assertRaises(ValueError):
                fact_kind(category=invalid)

    def test_past_state_references_queries_quotes_and_correction_are_not_consent(self):
        passages = (DECLARATION, '请解释已保存的病历', '请查询已经归档的资料',
            '可以使用已记录的背景', '请确认已保存的姓名', '我已经同意保存我的病历',
            '上次我确认保存我的病历', '是否可以保存我的病历？', '你可以记录这些信息吗？',
            '如果我同意保存我的病历', '请解释“请保存我的病历”这句话',
            '更正：“请保存我的病历”是旧原话', '他说：请保存我的病历',
            '更正：现在我的出生时间为08:15')
        for passage in passages:
            with self.subTest(passage=passage):
                self.assertFalse(explicit_save_authorization(passage))

    def test_actual_commands_remain_supported_and_refusal_has_priority(self):
        for passage in ('请保存我的背景', '请帮我记录我的背景', '请你记住我的约束',
            '同意保存我的背景', '我允许你记录我的背景', '授权系统保存我的背景',
            '确认保存我的背景', '可以留存我的背景', '保存这条背景', '记录我的背景',
            '请保存“本轮我提供的背景”'):
            with self.subTest(passage=passage):
                self.assertTrue(explicit_save_authorization(passage))
        for passage in ('不要保存。请保存我的背景', '请保存我的背景，但不允许记录这条',
                         '不需要长期保存。请记住我的背景'):
            with self.subTest(passage=passage):
                self.assertFalse(explicit_save_authorization(passage))

    def test_source_policy_defaults_false_and_rejects_coerced_model_flags(self):
        self.assertFalse(SourcePolicy().run_context)
        self.assertEqual(SourcePolicy().origin, 'unknown')
        self.assertTrue(SourcePolicy(run_context=True, origin='current_user').run_context)
        with self.assertRaises(ValidationError):
            SourcePolicy(run_context='true', origin='current_user')


class CurrentSourceAuthorizationPG(unittest.TestCase):
    def setUp(self):
        self.schema = 'test_current_source_' + uuid.uuid4().hex[:16]
        self.repo = PostgresRepository(test_dsn(), schema=self.schema, max_size=4)
        self.repo.ensure_owner('alpha')
        self.repo.ensure_owner('beta')
        self.model = SourceProvider()
        self.service = ConsultationService(self.repo, model=self.model)
        self.memory = self.service.memory

    def tearDown(self):
        with self.repo.connection() as connection:
            runs = connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch'] + 1):
                self.service.runtime.purge(run['id'], epoch)
        with self.repo.connection() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def source(self, content, **kwargs):
        return self.memory.receive('alpha', content=content, source_id=uuid.uuid4().hex, **kwargs)

    def proposal(self, quote, **kwargs):
        return dict(quote=quote, category='背景', field=None, value=None, **kwargs)

    def context(self, source, proposals, **kwargs):
        return self.memory.current_source_context('alpha', kwargs.pop('subject', 'self'), source['id'], proposals, **kwargs)

    def test_literal_recorded_card_and_medical_queries_do_not_save_or_grant_consent(self):
        for text in (DECLARATION, '请解释已保存的病历，我最近有压力', '更正：我现在的收入为合成2000'):
            with self.subTest(text=text):
                source = self.source(text)
                result = self.memory.save_fact('alpha', 'self', source['id'], text, 'background')
                self.assertEqual(result['write_status'], 'pending_confirmation')
                with self.assertRaises(EvidenceError):
                    self.memory.grant_authorization('alpha', 'self', source['id'], text)
        self.assertEqual(self.repo.list('alpha', 'fact'), [])
        self.assertEqual(self.repo.list('alpha', 'consent'), [])

    def test_explicit_sensitive_command_retains_durable_permission_without_context_flag(self):
        text = '请保存我的合成病历内容为待核实的症状记录'
        source = self.source(text, origin='migration')
        self.assertFalse(source['policy']['run_context'])
        grant = self.memory.grant_authorization('alpha', 'self', source['id'], text, kinds=['background'])
        result = self.memory.save_fact('alpha', 'self', source['id'], text, 'background', authorization_id=grant['id'])
        self.assertEqual(result['write_status'], 'saved')
        self.assertEqual(self.context(source, [self.proposal(text)])['facts'], [])

    def test_current_context_is_source_only_stable_no_fact_version_or_profile(self):
        source = self.source(MESSAGE)
        proposals = [self.proposal(BACKGROUND), self.proposal(DECLARATION)]
        before = self.repo.get_revision('alpha')
        context = self.context(source, proposals)
        again = self.context(source, proposals)
        self.assertEqual(context, again)
        self.assertEqual(len(context['facts']), 2)
        self.assertEqual([f['content'] for f in context['facts']], [BACKGROUND, DECLARATION])
        self.assertTrue(all(f['id'].startswith('current_source_') for f in context['facts']))
        self.assertTrue(all(f['context_only'] and f['assertion_status'] == 'current_source' and
            f['consent'] == 'current_round' and f['field'] is None and f['value'] is None for f in context['facts']))
        self.assertEqual(context['versions'], {'message:' + source['id']: source['revision']})
        self.assertEqual(self.repo.get_revision('alpha'), before)
        self.assertEqual(self.repo.list('alpha', 'fact'), [])
        self.assertEqual(self.memory.snapshot('alpha')['profile'], {})
        for fact in context['facts']:
            ref = fact['source_refs'][0]
            self.assertEqual(source['content'][ref['start']:ref['end']], ref['quote'])

    def test_saved_current_spans_excluded_but_low_sensitivity_policy_unchanged(self):
        source = self.source('我喜欢简短回答。' + BACKGROUND)
        fact = self.memory.save_fact('alpha', 'self', source['id'], '我喜欢简短回答', 'preference')
        self.assertEqual(fact['write_status'], 'saved')
        result = self.context(source, [self.proposal('我喜欢简短回答'), self.proposal(BACKGROUND)])
        self.assertEqual([f['content'] for f in result['facts']], [BACKGROUND])
        self.assertEqual(len(self.memory.facts('alpha')), 1)

    def test_system_report_sources_cannot_auto_save_user_preferences(self):
        quote = '我喜欢简短回答'
        for channel, origin in (('scheduled_report', 'current_user'), ('web', 'system')):
            with self.subTest(channel=channel, origin=origin):
                source = self.source(quote + '。', channel=channel, origin=origin)
                self.assertEqual(source['role'], 'user')
                self.assertEqual(source['policy']['origin'], 'system')
                before = self.repo.get_revision('alpha')
                result = self.memory.save_fact('alpha', 'self', source['id'], quote, category='preference')
                self.assertEqual(result['write_status'], 'rejected')
                self.assertIn('系统任务', result['reason'])
                self.assertEqual(self.memory.auto_preferences('alpha', 'self', source['id']), [])
                self.assertEqual(self.repo.get_revision('alpha'), before)
                self.assertEqual(self.context(source, [self.proposal(quote)])['facts'], [])
        refused = self.source('不要保存。' + quote, channel='scheduled_report')
        self.assertEqual(self.memory.save_fact('alpha', 'self', refused['id'], quote, 'preference'),
                         {'write_status': 'rejected', 'reason': '本轮明确要求不保存长期记忆'})
        self.assertEqual(self.repo.list('alpha', 'fact'), [])

    def test_optout_precedes_explicit_save_but_current_round_quote_is_available(self):
        text = '不要保存这些资料。' + BACKGROUND
        source = self.source(text)
        self.assertEqual(self.memory.save_fact('alpha', 'self', source['id'], BACKGROUND, 'background')['write_status'], 'rejected')
        self.assertEqual(self.context(source, [self.proposal(BACKGROUND)])['facts'][0]['content'], BACKGROUND)
        self.assertEqual(self.repo.list('alpha', 'fact'), [])

    def test_profile_secret_hypothesis_and_unknown_attributes_are_not_temporary_facts(self):
        source = self.source('假如我已确诊疾病，先讨论。我的生日为2000-01-01。密码为synthetic-only。')
        proposals = [self.proposal('我已确诊疾病'),
            {'quote': '我的生日为2000-01-01', 'category': '出生资料', 'field': None, 'value': None},
            {'quote': '我的生日为2000-01-01', 'category': '背景', 'field': 'birth.solar_datetime', 'value': '2000-01-01'},
            self.proposal('密码为synthetic-only')]
        self.assertEqual(self.context(source, proposals)['facts'], [])
        with self.assertRaises(EvidenceError):
            self.context(source, [dict(self.proposal('我的生日为2000-01-01'), confirmed=True)])
        self.assertEqual(self.memory.snapshot('alpha')['profile'], {})

    def test_historical_imports_system_sources_and_missing_policy_remain_false(self):
        for role, channel, origin in (('user', 'web', 'migration'), ('user', 'migration', 'current_user'),
                ('assistant', 'web', 'current_user'), ('tool', 'synthetic', 'current_user'),
                ('legacy', 'migration', 'current_user'), ('user', 'scheduled_report', 'current_user')):
            with self.subTest(role=role, channel=channel):
                source = self.source(BACKGROUND, role=role, channel=channel, origin=origin)
                self.assertFalse(source['policy']['run_context'])
                self.assertEqual(self.context(source, [self.proposal(BACKGROUND)])['facts'], [])
        source = self.memory.import_message('alpha', 'web', 'history-policy', 'user', BACKGROUND)
        received = self.memory.receive('alpha', content=BACKGROUND, source_id='history-policy', origin='current_user')
        self.assertEqual(source['id'], received['id'])
        self.assertFalse(received['policy']['run_context'])
        with self.repo.transaction('alpha') as connection:
            connection.execute(sql.SQL("UPDATE {} SET data=data-'policy' WHERE owner=%s AND id=%s").format(
                self.repo.table('core_entities')), ('alpha', received['id']))
        self.assertEqual(self.context(received, [self.proposal(BACKGROUND)])['facts'], [])

    def test_exact_quote_scope_and_selected_case_required(self):
        case = self.memory.create_case('alpha', 'self', '合成事项A')
        other = self.memory.create_case('alpha', 'self', '合成事项B')
        source = self.source(BACKGROUND, case_ids=[case['id']])
        with self.assertRaises(EvidenceError):
            self.context(source, [self.proposal(BACKGROUND + '，结果已确定')], case_ids=[case['id']])
        with self.assertRaises(ScopeError):
            self.context(source, [self.proposal(BACKGROUND, case_id=other['id'])], case_ids=[case['id']])
        with self.assertRaises(ScopeError):
            self.memory.current_source_context('beta', 'self', source['id'], [self.proposal(BACKGROUND)])
        result = self.context(source, [self.proposal(BACKGROUND, case_id=case['id'])], case_ids=[case['id']])
        self.assertEqual(result['facts'][0]['case_id'], case['id'])

    def test_third_person_permission_and_subject_isolation_remain_separate(self):
        self.repo.create_subject('alpha', 'other', '另一个合成人物')
        source = self.source('他已经确诊合成疾病')
        self.assertEqual(self.memory.save_fact('alpha', 'self', source['id'], source['content'], 'background')['write_status'], 'pending_confirmation')
        self.assertEqual(self.context(source, [self.proposal(source['content'])])['facts'], [])
        other = self.memory.receive('alpha', 'other', '合成人物最近有压力', source_id='other-round')
        self.assertEqual(self.memory.save_fact('alpha', 'other', other['id'], other['content'], 'background')['write_status'], 'pending_confirmation')
        self.assertEqual(len(self.context(other, [self.proposal(other['content'])], subject='other')['facts']), 1)
        with self.assertRaises(ScopeError):
            self.context(other, [self.proposal(other['content'])])
        explicit = self.memory.receive('alpha', 'other', '请保存合成人物最近有压力', source_id='other-save')
        self.assertEqual(self.memory.save_fact('alpha', 'other', explicit['id'], explicit['content'], 'background')['write_status'], 'saved')

    def test_correction_continues_only_its_existing_fact_permission(self):
        source = self.source('请保存我的出生时间为2000-01-01 08:00')
        old = self.memory.save_fact('alpha', 'self', source['id'], source['content'], 'profile',
                                   field='birth.solar_datetime', value='2000-01-01 08:00')
        quote = '更正：我的出生时间为2000-01-01 09:00'
        correction = self.source(quote + '。请解释已保存的病历，我最近有压力')
        changed = self.memory.correct_fact('alpha', old['id'], correction['id'], quote,
            expected_revision=old['revision'], value='2000-01-01 09:00', operation_id='same-fact-correction')
        self.assertEqual(changed['write_status'], 'saved')
        extra = self.memory.save_fact('alpha', 'self', correction['id'], '我最近有压力', 'background')
        self.assertEqual(extra['write_status'], 'pending_confirmation')
        self.assertEqual(len(self.memory.facts('alpha')), 1)

    def test_context_disappears_after_source_delete_or_span_withdrawal(self):
        source = self.source('我喜欢简短回答。' + BACKGROUND)
        preference = self.memory.save_fact('alpha', 'self', source['id'], '我喜欢简短回答', 'preference')
        self.assertEqual(len(self.context(source, [self.proposal(BACKGROUND)])['facts']), 1)
        self.memory.retire_fact('alpha', preference['id'], expected_revision=preference['revision'], scope='source')
        self.assertEqual(self.context(source, [self.proposal(BACKGROUND)])['facts'], [])
        fresh = self.source(BACKGROUND)
        self.assertEqual(len(self.context(fresh, [self.proposal(BACKGROUND)])['facts']), 1)
        with self.repo.transaction('alpha') as connection:
            self.repo.revoke(connection, 'alpha', 'source_span', 'synthetic-context-span', 'stopped',
                metadata={'message_id': fresh['id'], 'start': 0, 'end': len(BACKGROUND)})
        self.assertEqual(self.context(fresh, [self.proposal(BACKGROUND)])['facts'], [])

    def test_real_manual_tarot_core_round_keeps_nine_facts_and_context_ids_stable(self):
        for index in range(9):
            source = self.source('我喜欢合成主题' + str(index))
            self.memory.save_fact('alpha', 'self', source['id'], source['content'], 'preference')
        case = self.memory.create_case('alpha', 'self', '实体牌合成反思')
        draw = self.service.tarot.create_draw('alpha', subject_id='self', case_id=case['id'],
            question='比较合成白天安排', spread_id='reflect3', draw_source='manual',
            manual_cards=[{'card_id': 'major-00', 'orientation': 'upright'},
                          {'card_id': 'cups-01', 'orientation': 'reversed'},
                          {'card_id': 'pentacles-08', 'orientation': 'upright'}], idempotency_key='same-physical-cards')['draw']
        draw = self.service.tarot.reveal('alpha', draw['id'])
        self.model.tarot = True
        self.model.proposals = [self.proposal(BACKGROUND), self.proposal(DECLARATION)]
        run = self.service.submit(owner='alpha', message=MESSAGE, request_id='recorded-card-reference',
            draw_id=draw['id'], depth='standard')
        result = self.service.execute('alpha', run['id'])
        self.assertEqual(result['validation']['status'], 'validated')
        self.assertEqual([receipt['write_status'] for receipt in result['memory_receipts']], ['pending_confirmation'] * 2)
        self.assertEqual(len(self.repo.list('alpha', 'fact')), 9)
        synthesis = next(row['payload']['reference_data'] for row in self.model.requests if row['purpose'] == 'synthesis')
        temporary = [f for f in synthesis['facts'] if f.get('context_only')]
        self.assertEqual({f['content'] for f in temporary}, {BACKGROUND, DECLARATION})
        self.assertTrue({f['id'] for f in temporary} <= set(result['cited_fact_ids']))
        current = self.repo.fetch_run('alpha', run['id'])
        self.assertEqual(current['calls'], 3)
        self.assertFalse(any(key.startswith('fact:current_source_') for key in current['dependencies']))
        self.assertEqual(self.service.tarot.get('alpha', draw['id'])['cards'], draw['cards'])
        self.assertEqual(self.service.execute('alpha', run['id']), result)
        self.assertEqual(len(self.model.requests), 3)
        self.assertEqual(len(self.repo.list('alpha', 'fact')), 9)

    def test_unknown_citation_is_rejected_without_inventing_fact_binding(self):
        self.model.proposals = [self.proposal(BACKGROUND)]
        self.model.unknown_citation = True
        run = self.service.submit(owner='alpha', message=BACKGROUND, request_id='unknown-source-cite', depth='standard')
        with self.assertRaises(InvalidAnswer):
            self.service.execute('alpha', run['id'])
        self.assertIsNone(self.repo.fetch_run('alpha', run['id'])['result'])
        self.assertEqual(self.repo.list('alpha', 'fact'), [])

    def test_question_fragment_hypothesis_stays_current_only_not_auto_preference(self):
        message='请判断“付款无损失”是否有依据？'
        proposal={'quote':'付款无损失','category':'hypothesis','field':None,'value':None}
        self.model.proposals=[proposal]
        run=self.service.submit(owner='alpha',message=message,request_id='question-hypothesis',depth='fast')
        result=self.service.execute('alpha',run['id'])
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(result['memory_receipts'][0]['write_status'],'pending_confirmation')
        self.assertEqual(self.repo.list('alpha','fact'),[])
        data=next(row['payload']['reference_data'] for row in self.model.requests if row['purpose']=='synthesis')
        current=[fact for fact in data['facts'] if fact.get('context_only')]
        self.assertEqual(len(current),1)
        self.assertEqual((current[0]['kind'],current[0]['content']),('hypothesis','付款无损失'))
        self.assertEqual(current[0]['assertion_status'],'current_source')

    def test_unknown_category_cannot_fall_back_to_low_sensitivity_preference(self):
        source=self.source(BACKGROUND)
        for category in ('unknown-category','Background',''):
            with self.subTest(category=category),self.assertRaises(ValueError):
                self.memory.save_fact('alpha','self',source['id'],BACKGROUND,category=category)
            with self.subTest(context_category=category),self.assertRaises(ValueError):
                self.context(source,[{'quote':BACKGROUND,'category':category,'field':None,'value':None}])
        self.assertEqual(self.repo.list('alpha','fact'),[])

    def test_hermes_sync_historical_and_verified_current_consult_have_distinct_origin(self):
        self.repo.bind_channel('alpha', 'hermes-test', 'synthetic-author')
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as temporary:
            directory = Path(temporary).resolve()
            self.assertTrue(directory.is_relative_to(Path(__file__).resolve().parents[2]))
            dbpath = directory / 'sources.db'
            with closing(sqlite3.connect(dbpath)) as db:
                db.execute('CREATE TABLE sessions(id TEXT,source TEXT,user_id TEXT,chat_id TEXT,chat_type TEXT)')
                db.execute('CREATE TABLE messages(id TEXT,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER)')
                db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)', ('s', 'hermes-test', 'synthetic-author', 'chat', 'dm'))
                db.executemany('INSERT INTO messages VALUES(?,?,?,?,?,?)',
                    [('old', 's', 'user', '旧合成背景', 1791700000, 1),
                     ('current', 's', 'user', BACKGROUND, 1791700001, 1)])
                db.commit()
            adapter = HermesChannelAdapter(directory, service=self.service, hermes_db=dbpath)
            self.model.proposals = [self.proposal(BACKGROUND)]
            result = asyncio.run(adapter.consult(channel='hermes-test', external_id='synthetic-author',
                message_id='current', request_id='hermes-current', depth='fast'))
            self.assertTrue(result['validation']['valid'])
            sources = {row['content']: row for row in self.repo.list('alpha', 'message')}
            self.assertFalse(sources['旧合成背景']['policy']['run_context'])
            self.assertTrue(sources[BACKGROUND]['policy']['run_context'])
            self.assertEqual(self.repo.list('alpha', 'fact'), [])
            with self.assertRaises(ScopeError):
                asyncio.run(adapter.consult(channel='hermes-test', external_id='unbound-author', message_id='current'))

    def test_feishu_verified_current_origin_and_auth_binding_no_delivery(self):
        self.repo.bind_channel('alpha', 'feishu', 'ou_syntheticAuthor')
        gateway = FeishuGateway(self.service, transport=lambda *args: self.fail('No test sends'))
        event = {'header': {'event_type': 'im.message.receive_v1'}, 'event': {
            'sender': {'sender_type': 'user', 'sender_id': {'open_id': 'ou_syntheticAuthor'}},
            'message': {'message_id': 'om_syntheticSourcePolicy', 'chat_id': 'oc_syntheticPrivate',
                        'chat_type': 'p2p', 'message_type': 'text', 'content': json.dumps({'text': BACKGROUND})}}}
        accepted = gateway.accept(event)
        source = self.repo.get('alpha', 'message', self.repo.get('alpha', 'request', accepted['inbound_id'])['source_id'])
        self.assertEqual(source['policy'], {'run_context': True, 'origin': 'current_user'})
        self.assertEqual(self.model.requests, [])
        self.assertEqual(self.repo.list('alpha', 'delivery'), [])
        forged = deepcopy(event)
        forged['event']['sender']['sender_id']['open_id'] = 'ou_unboundAuthor'
        with self.assertRaises(ScopeError):
            gateway.accept(forged)
        self.assertEqual(len(self.repo.list('alpha', 'message')), 1)


if __name__ == '__main__':
    unittest.main()
