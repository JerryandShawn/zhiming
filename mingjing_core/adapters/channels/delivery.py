"""Send persisted Core outbox payloads without a second model interpretation.

The service owns the transactional claim, final revision checks, attempt limit
and reconciliation state. The transport is injected; importing this module or
preparing an outbox never performs network delivery.
"""
from __future__ import annotations

import inspect
from .hermes import render_channel


class TransportRejected(RuntimeError):
    """An explicit upstream rejection, rather than an ambiguous timeout."""


async def _resolved(value):
    return await value if inspect.isawaitable(value) else value


class CoreDeliveryWorker:
    def __init__(self, service, transport):
        if transport is None:
            raise ValueError("投递必须明确配置 transport，不能静默模拟成功")
        self.service = service
        self.transport = transport

    async def deliver(self, *, owner: str, outbox_id: str, now=None):
        # The service must reject stale, unauthorized, already sent or
        # uncertain events before returning a short-transaction claim.
        kwargs={'owner':owner,'outbox_id':outbox_id}
        if now is not None:kwargs['now']=now
        claim = await _resolved(self.service.claim_delivery(**kwargs))
        content = render_channel(claim["payload"])
        business_id = claim["business_id"]
        target = claim["target"]
        if not isinstance(business_id, str) or not business_id or not isinstance(target, str) or not target:
            raise ValueError("已领取事件缺少稳定业务编号或投递目标")
        try:
            receipt = await _resolved(self.transport(target, content, claim.get('transport_id', business_id)))
            if not isinstance(receipt, str) or not receipt.strip():
                raise RuntimeError("外部渠道没有返回可确认的消息 ID")
        except TransportRejected:
            # Do not record raw upstream bodies, which may contain credentials
            # or private report text. The service caps known-failure retries.
            return await _resolved(self.service.record_delivery(
                owner=owner, outbox_id=outbox_id, status="rejected",
                error="外部渠道明确拒绝本次投递",
                claim_token=claim['claim_token'],
            ))
        except Exception:
            # Unknown delivery can have succeeded remotely. It must not be
            # automatically claimed again, even under a different request ID.
            return await _resolved(self.service.record_delivery(
                owner=owner, outbox_id=outbox_id, status="uncertain",
                error="DELIVERY_UNCERTAIN：外部送达状态不明，需对账",
                claim_token=claim['claim_token'],
            ))
        return await _resolved(self.service.record_delivery(
            owner=owner, outbox_id=outbox_id, status="sent", message_id=receipt, claim_token=claim['claim_token'],
        ))

    async def reconcile(self, *, owner: str, outbox_id: str, delivered: bool, message_id=None, evidence_ref=None):
        if not isinstance(delivered, bool):
            raise ValueError("对账结果必须明确为已送达或未送达")
        if delivered and (not isinstance(message_id, str) or not message_id.strip()):
            raise ValueError("确认已送达必须提供真实外部消息 ID")
        # No transport call here. Reconciliation records verified external
        # evidence and explicitly unlocks only a proven-unsent event.
        return await _resolved(self.service.reconcile_delivery(
            owner=owner, outbox_id=outbox_id, delivered=delivered, message_id=message_id, evidence_ref=evidence_ref,
        ))
