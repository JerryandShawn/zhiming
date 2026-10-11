"""Exercise real v6 HTTP routes against an isolated local/staging account.

This script writes clearly marked synthetic records. It never imports the app,
patches routes, seeds databases, or calls a fake backend. The target must have AI
disabled so that the failure/static-reading path is deterministic. Use only a
disposable test account. Remote targets require --staging and a token environment
variable; the production site is explicitly rejected.

python tests/http_v6_smoke.py --base-url http://127.0.0.1:8766
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class HttpSmoke:
    def __init__(self, base, token):
        self.base, self.token = base.rstrip('/'), token
        self.run_id = 'HTTP_SMOKE_' + uuid.uuid4().hex[:12]
        self.checks, self.draw_ids = [], []
        self.started = time.monotonic()

    def call(self, path, method='GET', body=None, expected=200, auth=True):
        headers = {'X-Token': self.token} if auth else {}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
            headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                status, content_type, data = response.status, response.headers.get('Content-Type', ''), response.read()
        except urllib.error.HTTPError as error:
            status, content_type, data = error.code, error.headers.get('Content-Type', ''), error.read()
        allowed = expected if isinstance(expected, tuple) else (expected,)
        route = re.sub(r'(?<=/)(?:fact_|case_)?[a-f0-9]{20,}', '{id}', path.split('?')[0])
        assert status in allowed, f'{method} {route}: expected HTTP {allowed}; received HTTP {status}'
        if 'text/event-stream' in content_type:
            return [json.loads(line[5:].strip()) for line in data.decode().splitlines()
                    if line.startswith('data:') and line[5:].strip() != '[DONE]']
        if 'json' in content_type:
            return json.loads(data)
        return data

    def check(self, name, action):
        start = time.monotonic()
        try:
            action()
            row = {'name': name, 'status': 'passed'}
        except Exception as error:
            # Assertion diagnostics are predefined and contain no response data.
            detail = str(error) if isinstance(error, AssertionError) else type(error).__name__
            row = {'name': name, 'status': 'failed', 'detail': detail[:300]}
        row['elapsed_ms'] = round((time.monotonic() - start) * 1000)
        self.checks.append(row)
        print(f"{row['status'].upper()}: {name}" + (f" ({row['detail']})" if 'detail' in row else ''), flush=True)

    def revision(self):
        return self.call('/api/state')['revision']

    def run(self):
        def health():
            data = self.call('/api/health')
            assert data['ok'] is True and data['context_version'] == '6.0', 'v6 health is unavailable'
            assert data['daily_schedule'] == '07:00', 'Daily schedule is not 07:00'
            self.call('/api/state', auth=False, expected=401)
        self.check('health_schedule_and_auth', health)

        def deck():
            self.deck = self.call('/api/tarot/deck')
            cards = self.deck['cards']
            assert len(cards) == len({c['card_id'] for c in cards}) == 78, 'Deck is not 78 unique cards'
            assert {s['id'] for s in self.deck['spreads']} == {'focus1', 'reflect3', 'choice5'}, 'Required spreads missing'
            paths = [c.get('image_url') or c['image'] for c in cards] + [self.deck['back_image']]
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                images = list(pool.map(self.call, paths))
            assert all(isinstance(data, bytes) and b'<svg' in data for data in images), 'An SVG HTTP response is invalid'
            assert all(c['name'] and c['upright'] and c['reversed'] and c['misreading'] and c['question'] for c in cards), 'Static reading content missing'
        self.check('deck_and_all_78_cards_plus_back_http_200', deck)
        if not hasattr(self, 'deck'):
            return

        def create_case():
            self.case = self.call('/api/cases', 'POST', {'title': self.run_id + ' 合成测试事项', 'goal': '验证接口一致性', 'subject_id': 'self', 'request_id': uuid.uuid4().hex})
            assert self.case['id'] in {c['id'] for c in self.call('/api/cases')}, 'Created case is not listed'
        self.check('case_create_and_list', create_case)
        if not hasattr(self, 'case'):
            return

        def draw_flow(spread_id, source):
            spread = next(s for s in self.deck['spreads'] if s['id'] == spread_id)
            count = len(spread['positions'])
            body = {'question': self.run_id + f' {spread_id} {source} 如何安排本周阅读？', 'spread_id': spread_id,
                    'draw_source': source, 'reversals': True, 'options': {'A': '保留安排', 'B': '减少任务'} if count == 5 else {},
                    'background': '这是隔离账号中的合成接口测试。', 'case_id': self.case['id'], 'subject_id': 'self',
                    'idempotency_key': uuid.uuid4().hex, 'explicit_new': True,
                    **({'previous_draw_id': self.draw_ids[-1]} if self.draw_ids else {})}
            if source == 'manual':
                body['manual_cards'] = [{'card_id': c['card_id'], 'orientation': 'reversed' if i % 2 else 'upright'} for i, c in enumerate(self.deck['cards'][:count])]
            # A real concurrent double submission, not a sequential stub replay.
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                first, second = list(pool.map(lambda _: self.call('/api/tarot/draws', 'POST', body), range(2)))
            draw = first['draw']
            assert draw['id'] == second['draw']['id'], 'Double submission created different draws'
            ident = draw['id']; self.draw_ids.append(ident)
            assert draw['options'] == body['options'], 'Frozen options changed'
            assert draw['context_snapshot']['background'] == body['background'], 'Background was not frozen'
            assert all(not card.get('card_id') and not card.get('orientation') for card in draw['cards']), 'Hidden cards expose their identity'
            self.call('/api/tarot/draws', 'POST', dict(body, question='changed request'), expected=400)
            if source == 'pick':
                assert len(draw['backs']) == 78, 'Pick draw does not expose 78 opaque backs'
                assert all(set(back) <= {'back_id', 'id', 'selected'} for back in draw['backs']), 'Backs expose private card fields'
                for back in draw['backs'][:count]:
                    selection = {'back_id': back.get('back_id') or back['id'], 'idempotency_key': uuid.uuid4().hex}
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                        a, b = list(pool.map(lambda _: self.call(f'/api/tarot/draws/{ident}/select', 'POST', selection), range(2)))
                    assert len(a['cards']) == len(b['cards']), 'Replayed selection selected an extra card'
                assert len(a['cards']) == count, 'Selection count is wrong'
            # A hidden draw may not be sent to the model.
            self.call(f'/api/tarot/draws/{ident}/readings', 'POST', {'request_id': uuid.uuid4().hex}, expected=400)
            single = self.call(f'/api/tarot/draws/{ident}/reveal', 'POST', {'position': 1})
            assert single['cards'][0]['revealed'] is True, 'First-position reveal failed'
            revealed = self.call(f'/api/tarot/draws/{ident}/reveal', 'POST', {})
            restored = self.call(f'/api/tarot/draws/{ident}')
            signature = lambda d: [(c['position'], c['card_id'], c['orientation']) for c in d['cards']]
            assert revealed['status'] == restored['status'] == 'ready', 'Fully revealed draw is not ready'
            assert signature(revealed) == signature(restored), 'Restore changed fixed cards'
            assert len({c['card_id'] for c in restored['cards']}) == count, 'Cards are duplicated'
            assert all(c['card']['upright'] and c['card']['reversed'] for c in restored['cards']), 'Static card fallback missing'
            if source == 'manual':
                assert [c['card_id'] for c in restored['cards']] == [c['card_id'] for c in body['manual_cards']], 'Manual cards changed'
                self.manual = restored
            self.ready = restored
        for spread in ('focus1', 'reflect3', 'choice5'):
            for source in ('auto', 'pick', 'manual'):
                self.check(f'{spread}_{source}_double_submit_reveal_restore', lambda s=spread, d=source: draw_flow(s, d))

        def failed_reading():
            draw = self.ready; ident = draw['id']; key = uuid.uuid4().hex
            body = {'request_id': key, 'supplement': '合成测试补充事实'}
            events = self.call(f'/api/tarot/draws/{ident}/readings', 'POST', body)
            assert any(e['type'] == 'error' and '未配置' in e.get('message', '') for e in events), 'No-AI reading did not explicitly report unconfigured'
            assert not any(e['type'] == 'result' for e in events), 'Failed reading emitted a false result'
            started = next(e for e in events if e['type'] == 'started')
            rows = self.call(f'/api/tarot/draws/{ident}/readings')
            own = next(r for r in rows if r['id'] == started['reading_id'])
            assert own['status'] == 'failed' and not own['result'], 'Failed reading was stored as successful'
            assert own.get('request_id') == key, 'Reading request recovery key is missing'
            self.call(f'/api/tarot/draws/{ident}/readings', 'POST', body)
            assert len(self.call(f'/api/tarot/draws/{ident}/readings')) == len(rows), 'Same reading request created another version'
            self.call(f'/api/tarot/draws/{ident}/readings', 'POST', {'request_id': uuid.uuid4().hex, 'supplement': '第二次合成补充'})
            assert len(self.call(f'/api/tarot/draws/{ident}/readings')) == len(rows) + 1, 'New reading request did not create a version'
            restored = self.call(f'/api/tarot/draws/{ident}')
            assert [(c['card_id'], c['orientation']) for c in draw['cards']] == [(c['card_id'], c['orientation']) for c in restored['cards']], 'Reading retry changed cards'
        if hasattr(self, 'ready'):
            self.check('no_ai_sse_failed_versions_static_cards_and_replay', failed_reading)

        def fixed_draw_chat():
            draw = self.ready
            events = self.call('/api/chat', 'POST', {'message': '请接着解释第三张与现实安排的关系。', 'request_id': uuid.uuid4().hex,
                                                    'session_id': 'shared', 'case_id': draw['case_id'], 'draw_id': draw['id']})
            assert any(e['type'] == 'error' and '未配置' in e.get('message', '') for e in events), 'Linked no-AI chat did not report the actual model limitation'
            assert not any(e['type'] == 'result' for e in events), 'Linked no-AI chat emitted a false result'
            restored = self.call(f"/api/tarot/draws/{draw['id']}")
            assert [(c['card_id'], c['orientation']) for c in restored['cards']] == [(c['card_id'], c['orientation']) for c in draw['cards']], 'Main chat changed the linked draw'
        if hasattr(self, 'ready'):
            self.check('main_chat_uses_fixed_case_and_draw_without_false_success', fixed_draw_chat)

        def cancel_draw():
            body = {'question': self.run_id + ' 取消与正逆设置验证', 'spread_id': 'reflect3', 'draw_source': 'pick',
                    'case_id': self.case['id'], 'reversals': False, 'idempotency_key': uuid.uuid4().hex, 'explicit_new': True}
            draw = self.call('/api/tarot/draws', 'POST', body)['draw']; self.draw_ids.append(draw['id'])
            cancelled = self.call(f"/api/tarot/draws/{draw['id']}/cancel", 'POST', {})
            assert cancelled['status'] == 'cancelled', 'Cancellation did not persist'
            self.call(f"/api/tarot/draws/{draw['id']}/select", 'POST', {'back_id': draw['backs'][0]['back_id'], 'idempotency_key': uuid.uuid4().hex}, expected=400)
            self.call(f"/api/tarot/draws/{draw['id']}/readings", 'POST', {'request_id': uuid.uuid4().hex}, expected=400)
            preferences = self.call('/api/tarot/deck')['preferences']
            assert preferences['reversals'] is False, 'Reversal preference was not persisted'
        self.check('cancelled_draw_cannot_continue_selection_or_reading', cancel_draw)

        def feedback():
            path = f"/api/cases/{self.case['id']}/events"
            rev = self.revision()
            self.event = {'kind': 'decided', 'content': self.run_id + ' 我已经决定今天先读十页。', 'request_id': uuid.uuid4().hex, 'expected_revision': rev}
            self.call(path, 'POST', self.event)
            self.call(path, 'POST', dict(self.event, request_id=uuid.uuid4().hex), expected=409)
            self.call(path, 'POST', {'kind': 'acted', 'content': '合成操作缺少版本', 'request_id': uuid.uuid4().hex}, expected=409)
            self.call(path, 'POST', {'kind': 'acted', 'content': self.run_id + ' 我已经读完十页。', 'request_id': uuid.uuid4().hex, 'expected_revision': self.revision()})
            snap = self.call('/api/state')
            case = next(c for c in snap['cases'] if c['id'] == self.case['id'])
            assert any(e['kind'] == 'decided' for e in case.get('events', [])), 'Decision not visible in authoritative state'
        self.check('case_feedback_revision_conflict_and_authoritative_event', feedback)
        if hasattr(self, 'event'):
            self.check('case_feedback_lost_response_idempotent_replay', lambda: self.call(f"/api/cases/{self.case['id']}/events", 'POST', self.event))

        def create_memory(label):
            if not hasattr(self, 'session'):
                self.session = self.call('/api/sessions', 'POST', {'title': self.run_id + ' 合成测试对话'})['id']
            quote = '我喜欢把 ' + self.run_id + ' ' + label + ' 的步骤写成清单。'
            events = self.call('/api/chat', 'POST', {'message': quote, 'request_id': uuid.uuid4().hex, 'session_id': self.session})
            assert any(e['type'] == 'error' for e in events), 'Isolated no-AI chat did not return an explicit failure'
            facts = self.call('/api/memories')
            found = [f for f in facts if self.run_id + ' ' + label in f.get('text', '') and f['status'] == 'active']
            assert len(found) == 1, 'Explicit synthetic preference did not become one active fact'
            return found[0]

        def memories():
            memory = create_memory('fact_scope'); ident = memory['id']
            source = self.call(f'/api/memories/{ident}/source')
            assert source['source_available'] and any(self.run_id in s['content'] for s in source['sources']), 'Fact source is not the authorized user message'
            rev = self.revision()
            self.call(f'/api/memories/{ident}', 'PATCH', {'text': self.run_id + ' 更正为分两步阅读。', 'expected_revision': rev - 1}, expected=409)
            updated = self.call(f'/api/memories/{ident}', 'PATCH', {'text': self.run_id + ' 更正为分两步阅读。', 'expected_revision': rev})
            assert updated['id'] != ident and updated['status'] == 'active', 'Correction did not supersede the previous fact'
            ident = updated['id']
            self.call(f'/api/memories/{ident}', 'PATCH', {'status': 'hidden', 'expected_revision': self.revision()})
            self.call(f'/api/memories/{ident}', 'PATCH', {'status': 'active', 'expected_revision': self.revision()}, expected=409)
            self.call(f'/api/memories/{ident}?scope=fact&expected_revision={self.revision()}', 'DELETE')
            kept_source = self.call(f'/api/memories/{ident}/source')
            fact_only_source_available = kept_source['source_available'] and bool(kept_source['sources'])
            assert ident not in {f['id'] for f in self.call('/api/state')['facts']}, 'Deleted fact is still in active context'
            audit = self.call(f'/api/memories/{ident}/audit', expected=(200, 404))
            if isinstance(audit, list):
                assert all(set(row) <= {'operation', 'revision', 'at'} for row in audit), 'Deletion audit retains content'
            second = create_memory('source_scope'); second_id = second['id']
            self.call(f'/api/memories/{second_id}?scope=source&expected_revision={self.revision()}', 'DELETE')
            erased_source = self.call(f'/api/memories/{second_id}/source')
            assert erased_source['source_available'] is False and not erased_source['sources'], 'Source deletion left original content accessible'
            self.call('/api/memories/nonexistent-smoke-record/source', expected=404)
            self.call('/api/memories/nonexistent-smoke-record', 'PATCH', {'text': 'synthetic', 'expected_revision': self.revision()}, expected=404)
            assert fact_only_source_available, 'Fact-only deletion incorrectly hid the retained original source'
        self.check('memory_http_create_source_correct_stop_delete_and_error_states', memories)

        def manual_revision():
            draw = self.manual; new_cards = [{'card_id': c['card_id'], 'orientation': c['orientation']} for c in draw['cards']]
            new_cards[0] = {'card_id': self.deck['cards'][-1]['card_id'], 'orientation': 'upright'}
            body = {'cards': new_cards, 'reason': '合成测试：第一张实体牌录入有误。', 'idempotency_key': uuid.uuid4().hex}
            result = self.call(f"/api/tarot/draws/{draw['id']}/manual", 'PATCH', body)
            assert result['id'] != draw['id'] and result['previous_draw_id'] == draw['id'], 'Manual correction did not preserve a linked revision'
            self.draw_ids.append(result['id'])
            assert all(not c['revealed'] for c in result['cards']), 'Corrected cards unexpectedly reveal themselves'
            replay = self.call(f"/api/tarot/draws/{draw['id']}/manual", 'PATCH', body)
            assert replay['id'] == result['id'], 'Manual correction replay created another draw'
        if hasattr(self, 'manual'):
            self.check('manual_correction_new_revision_and_idempotency', manual_revision)

        def cleanup():
            remaining = {d['id'] for d in self.call('/api/tarot/draws')}
            for ident in self.draw_ids:
                if ident not in remaining:
                    continue
                result = self.call(f'/api/tarot/draws/{ident}', 'DELETE')
                remaining -= set(result.get('deleted_ids', [ident]))
                self.call(f'/api/tarot/draws/{ident}', expected=404)
            assert not set(self.draw_ids) & {d['id'] for d in self.call('/api/tarot/draws')}, 'Deleted test draws remain listed'
            self.call(f"/api/cases/{self.case['id']}", 'PATCH', {'changes': {'status': 'closed'}, 'expected_revision': self.revision()})
        self.check('delete_draws_and_close_synthetic_case', cleanup)

    def report(self):
        return {'schema': 'v6-http-smoke-1', 'target': self.base, 'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'backend': 'actual_http_routes', 'account': 'isolated_synthetic_test_account',
                'browser_used': False, 'model_success_tested': False,
                'elapsed_seconds': round(time.monotonic() - self.started, 2),
                'passed': sum(c['status'] == 'passed' for c in self.checks), 'failed': sum(c['status'] == 'failed' for c in self.checks),
                'checks': self.checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8766')
    parser.add_argument('--staging', action='store_true')
    parser.add_argument('--token-env', default='ZHIMING_TEST_TOKEN')
    parser.add_argument('--output', default='private/v6-preview/http-result.json')
    args = parser.parse_args()
    parsed = urllib.parse.urlparse(args.base_url)
    local = parsed.hostname in ('127.0.0.1', 'localhost', '::1')
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error('Use a plain local/staging URL without credentials or query parameters.')
    if parsed.hostname == 'p.jerrymeng.asia' or (not local and not args.staging):
        parser.error('Production targets are forbidden; remote disposable staging requires --staging.')
    token = os.environ.get(args.token_env) or ('preview-fixture-only' if local else '')
    if not token:
        parser.error('Set the disposable staging token through the selected environment variable.')
    smoke = HttpSmoke(args.base_url, token)
    smoke.run()
    report = smoke.report()
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'failed': report['failed'], 'report': str(output)}, ensure_ascii=False))
    raise SystemExit(1 if report['failed'] else 0)


if __name__ == '__main__':
    main()
