"""Direct Feishu DM entry: verified author -> Core -> validated outbox.

No Hermes agent, model tool wrapper or second interpretation is imported.
The SDK callback commits the original and queue before acknowledging it.
Background polling recovers accepted events after a process interruption.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import re
import threading

from psycopg import sql
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.repositories.postgres import fingerprint
from .channels.delivery import CoreDeliveryWorker
from .channels.feishu import FeishuTransport

LOG = logging.getLogger(__name__)


def _field(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


class FeishuGateway:
    def __init__(self, service, transport=None, *, max_concurrency=1):
        self.service = service
        self.repo = service.repo
        self.delivery = CoreDeliveryWorker(service, transport or FeishuTransport())
        self._locks = {}
        self._capacity=asyncio.Semaphore(max(1,min(int(max_concurrency),8)))

    def accept(self, data):
        """Durable intake only; never call a model or network from SDK callback."""
        header = _field(data, 'header')
        if header and _field(header, 'event_type') != 'im.message.receive_v1':
            return {'status': 'ignored', 'reason': 'unsupported_event'}
        event = _field(data, 'event')
        sender = _field(event, 'sender')
        message = _field(event, 'message')
        if _field(sender, 'sender_type') != 'user' or _field(message, 'chat_type') != 'p2p':
            return {'status': 'ignored', 'reason': 'only_user_direct_messages'}
        if _field(message, 'message_type') != 'text':
            return {'status': 'ignored', 'reason': 'only_text_supported'}
        author = _field(_field(sender, 'sender_id'), 'open_id')
        source_id = _field(message, 'message_id')
        chat_id = _field(message, 'chat_id')
        if not isinstance(author, str) or not re.fullmatch(r'ou_[A-Za-z0-9]+', author):
            raise ScopeError('飞书事件缺少有效的原始用户身份')
        if not isinstance(source_id, str) or not source_id or len(source_id) > 200:
            raise EvidenceError('飞书事件缺少稳定消息标识')
        if not isinstance(chat_id, str) or not re.fullmatch(r'oc_[A-Za-z0-9]+', chat_id):
            raise EvidenceError('飞书事件缺少有效私聊标识')
        try:
            content = json.loads(_field(message, 'content', ''))
        except (TypeError, ValueError) as exc:
            raise EvidenceError('飞书原话格式不可用') from exc
        text = content.get('text') if isinstance(content, dict) else None
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 16000:
            raise EvidenceError('飞书文本需要1至16000字')
        binding = self.repo.resolve_channel('feishu', author)
        if binding.get('binding_kind') != 'user':
            raise ScopeError('飞书原始作者必须有明确 user 绑定')
        owner, subject = binding['owner'], binding['subject']
        conversation = 'feishu:p2p:' + chat_id
        operation = 'feishu:message:' + source_id
        ident = 'feishu-inbound:' + fingerprint([owner, source_id])[:32]
        stamp = _field(message, 'create_time')
        try:
            at = datetime.fromtimestamp(int(stamp) / 1000, timezone.utc) if stamp is not None else None
        except (ValueError, TypeError, OverflowError) as exc:
            raise EvidenceError('飞书原始时间格式不可用') from exc
        with self.repo.transaction(owner):
            original = self.service.memory.receive(owner, subject, text, channel='feishu',
                       source_id=source_id, external_id=author, conversation_id=conversation, at=at)
            run = self.service.submit(owner=owner, subject=subject, message=text,
                      conversation_id=conversation, request_id=operation,
                      source_message_id=original['id'], mode='chat', depth='standard')
            self.repo.put(owner, 'request', ident, {'gateway': 'feishu', 'run_id': run['id'],
                          'source_id': original['id'], 'target': author,
                          'business_id': operation, 'chat_id': chat_id}, subject=subject,
                          operation_id='feishu-accept:' + source_id)
        return {'status': 'accepted', 'owner': owner, 'inbound_id': ident, 'run_id': run['id']}

    async def handle(self, data):
        accepted = self.accept(data)
        if accepted['status'] != 'accepted':
            return accepted
        return await self.process(accepted['owner'], accepted['inbound_id'])

    async def process(self, owner, inbound_id):
        async with self._capacity:
            return await self._process(owner,inbound_id)

    async def _process(self, owner, inbound_id):
        lock = self._locks.setdefault((owner, inbound_id), asyncio.Lock())
        async with lock:
            item = self.repo.get(owner, 'request', inbound_id)
            if item.get('gateway') != 'feishu':
                raise ScopeError('入口记录不是飞书原始事件')
            run = self.repo.fetch_run(owner, item['run_id'])
            if run['subject'] != item['subject_id']:
                raise ScopeError('入口执行人物与绑定不符')
            if run['status'] == 'queued':
                try:
                    await self.service.consult(owner=owner, subject=run['subject'],
                           request_id=run['operation_id'], **run['request'])
                except LeaseConflict:
                    # A web recovery worker can legitimately own this run.
                    pass
                run = self.repo.fetch_run(owner, item['run_id'])
            if run['status'] != 'succeeded':
                return {'status': run['status'], 'run_id': run['id']}
            with self.repo.connection() as connection:
                persisted = connection.execute(sql.SQL('SELECT id,status FROM {} WHERE owner=%s AND business_id=%s AND channel=%s AND target=%s').format(self.repo.table('delivery_outbox')),
                            (owner,item['business_id'],'feishu',item['target'])).fetchone()
            if persisted and persisted['status'] not in ('pending','rejected'):
                self._delivery_state(owner,inbound_id,persisted['status'])
                return {'status':persisted['status'],'run_id':run['id'],'outbox_id':persisted['id']}
            outbox = self.service.prepare_delivery(owner=owner, run_id=run['id'],
                        business_id=item['business_id'], channel='feishu', target=item['target'])
            if outbox['status'] not in ('pending', 'rejected'):
                self._delivery_state(owner,inbound_id,outbox['status'])
                return {'status': outbox['status'], 'run_id': run['id'], 'outbox_id': outbox['id']}
            receipt = await self.delivery.deliver(owner=owner, outbox_id=outbox['id'])
            self._delivery_state(owner,inbound_id,receipt['status'])
            return {'status': receipt['status'], 'run_id': run['id'], 'outbox_id': outbox['id']}

    def _delivery_state(self,owner,inbound_id,status):
        with self.repo.transaction(owner):
            item=self.repo.get(owner,'request',inbound_id)
            if item.get('delivery_status')!=status:
                self.repo.update(owner,'request',inbound_id,{'delivery_status':status},expected_revision=item['revision'])

    async def tick(self):
        """Recover persisted incoming events; an uncertain send is never replayed."""
        with self.repo.connection() as connection:
            rows = connection.execute(sql.SQL("SELECT owner,id FROM {} WHERE kind='request' AND status='active' AND data->>'gateway'='feishu' AND COALESCE(data->>'delivery_status','pending') IN ('pending','rejected','sending') ORDER BY created_at LIMIT 10000").format(self.repo.table('core_entities'))).fetchall()
        for owner in {row['owner'] for row in rows}:
            self.repo.recover_runs(owner)
            self.service.outbox.recover_claims(owner)
        counts = {'processed': 0, 'failed': 0}
        for row in rows:
            try:
                await self.process(row['owner'], row['id'])
                counts['processed'] += 1
            except Exception as exc:
                counts['failed'] += 1
                # Never log SDK event objects, model output or upstream bodies.
                LOG.warning('Core Feishu processing stopped: %s', getattr(exc, 'code', type(exc).__name__))
        return counts


def build_sdk_client(callback, *, app_id, app_secret, sdk=None):
    """Build the official WS receiver without opening any connection."""
    if not app_id or not app_secret:
        raise ValueError('飞书应用配置缺失')
    if sdk is None:
        import lark_oapi as sdk
    handler = sdk.EventDispatcherHandler.builder('', '').register_p2_im_message_receive_v1(callback).build()
    return sdk.ws.Client(app_id, app_secret, event_handler=handler, log_level=sdk.LogLevel.ERROR)


class FeishuGatewayRunner:
    """SDK main loop plus a separate async Core worker loop."""
    def __init__(self, gateway, *, poll_seconds=5):
        self.gateway = gateway
        self.poll_seconds = max(1, int(poll_seconds))
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name='core-feishu-worker', daemon=True)

    def callback(self, event):
        try:
            accepted = self.gateway.accept(event)
            if accepted['status'] == 'accepted':
                future = asyncio.run_coroutine_threadsafe(self.gateway.process(accepted['owner'], accepted['inbound_id']), self.loop)
                future.add_done_callback(self._completed)
        except (ScopeError, EvidenceError, ValueError) as exc:
            LOG.warning('Core Feishu intake rejected: %s', getattr(exc, 'code', type(exc).__name__))

    @staticmethod
    def _completed(future):
        try:
            future.result()
        except Exception as exc:
            LOG.warning('Core Feishu event pending recovery: %s', getattr(exc, 'code', type(exc).__name__))

    async def _poll(self):
        while True:
            try:
                await self.gateway.tick()
            except Exception as exc:
                LOG.warning('Core Feishu poll stopped: %s', getattr(exc, 'code', type(exc).__name__))
            await asyncio.sleep(self.poll_seconds)

    def start(self, *, app_id, app_secret):
        # This lock prevents two Core receiver processes using the same app.
        # The release operator must disable the old Hermes Feishu receiver first.
        with self.gateway.repo.pool.connection() as connection:
            lock_key = self.gateway.repo.schema + ':feishu-gateway:' + app_id
            acquired = connection.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired', (lock_key,)).fetchone()['acquired']
            if not acquired:
                raise LeaseConflict('同一飞书应用已有 Core 接收进程')
            try:
                client = build_sdk_client(self.callback, app_id=app_id, app_secret=app_secret)
                self.thread.start()
                poll = asyncio.run_coroutine_threadsafe(self._poll(), self.loop)
                client.start()
            finally:
                if self.thread.is_alive():
                    poll.cancel()
                    self.loop.call_soon_threadsafe(self.loop.stop)
                    self.thread.join(timeout=5)
                connection.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))', (lock_key,))


def main():
    if os.environ.get('CORE_FEISHU_ENABLED', '').lower() not in ('1', 'true', 'yes'):
        raise RuntimeError('Core 飞书入口尚未显式启用')
    from mingjing_core.application.consultation import ConsultationService
    service = ConsultationService.from_base()
    try:
        FeishuGatewayRunner(FeishuGateway(service)).start(
            app_id=os.environ['FEISHU_APP_ID'], app_secret=os.environ['FEISHU_APP_SECRET'])
    finally:
        service.repo.close()


if __name__ == '__main__':
    main()
