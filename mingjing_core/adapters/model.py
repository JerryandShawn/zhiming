"""Existing configured Anthropic-compatible provider, without tool orchestration."""
import json
import os
import time
import base64
import httpx
from ..domain.consultation import ModelUnavailable, ModelFailureReason


class ConfiguredModel:
    def __init__(self, key=None, base=None, model=None):
        self.key = key if key is not None else os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY", "")
        self.base = (base or os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")).rstrip("/")
        self.model = model or os.getenv("KIMI_MODEL", "kimi-k3")

    def generate(self, *, system, payload, schema, purpose):
        if not self.key:
            raise ModelUnavailable("模型尚未配置；已保存的问题与固定牌阵可以恢复", reason=ModelFailureReason.CONFIGURATION)
        started = time.monotonic()
        headers = {"x-api-key": self.key, "anthropic-version": "2023-06-01", "User-Agent": "MingjingCore/3.0"}
        reference = dict(payload)
        images = reference.pop('_image_inputs', [])
        content = [{"type": "text", "text": json.dumps(reference, ensure_ascii=False, allow_nan=False)}]
        for image in images:
            content.append({"type": "image", "source": {"type": "base64", "media_type": image['mime'], "data": image['data']}})
        body = {"model": self.model, "system": system,
                "messages": [{"role": "user", "content": content}],
                "tools": [{"name": "submit", "description": "提交本阶段的结构化结果", "input_schema": schema}],
                "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
                "max_tokens": 14000 if purpose in ("synthesis", "review", "repair") else 6000,
                "temperature": 1, "thinking": {"type": "enabled", "budget_tokens": 1024}}
        network_failed = False
        try:
            with httpx.Client(timeout=httpx.Timeout(240, connect=20), follow_redirects=False) as client:
                response = client.post(self.base + "/messages", headers=headers, json=body)
        except httpx.HTTPError:
            network_failed = True
        if network_failed:
            # Raise after leaving the handler: do not attach a provider error
            # containing request URLs, headers or response text as the cause.
            raise ModelUnavailable("模型服务连接中断；调用预算已记录，可恢复同一请求",
                                   reason=ModelFailureReason.NETWORK, latency_seconds=time.monotonic() - started)
        status = response.status_code
        if status != 200:
            raise ModelUnavailable(f"模型服务返回 HTTP {status}；本轮结果尚未提交",
                                   reason=ModelFailureReason.HTTP, provider_http_status=status,
                                   latency_seconds=time.monotonic() - started)
        parsed = None
        try:
            parsed = response.json()
        except ValueError:
            pass
        if not isinstance(parsed, dict):
            raise ModelUnavailable("模型服务返回格式不可用；本轮结果尚未提交",
                                   reason=ModelFailureReason.JSON, provider_http_status=status,
                                   latency_seconds=time.monotonic() - started)
        diagnostic = {'provider_http_status':status, 'usage':parsed.get('usage'),
                      'latency_seconds':time.monotonic() - started, 'stop_reason':parsed.get('stop_reason')}
        blocks = parsed.get('content', [])
        if not isinstance(blocks, list) or any(not isinstance(block, dict) for block in blocks):
            raise ModelUnavailable("模型服务返回格式不可用；本轮结果尚未提交",
                                   reason=ModelFailureReason.JSON, **diagnostic)
        if parsed.get("stop_reason") == "max_tokens":
            raise ModelUnavailable("模型输出超出本次上限；未展示未核验结果", reason=ModelFailureReason.MAX_TOKENS, **diagnostic)
        calls = [c for c in blocks if c.get("type") == "tool_use" and c.get("name") == "submit"]
        if len(calls) != 1:
            raise ModelUnavailable("模型未返回唯一结构化结果；本次调用已计入预算",
                                   reason=ModelFailureReason.TOOL_COUNT, tool_count=len(calls), **diagnostic)
        if not isinstance(calls[0].get("input"), dict):
            raise ModelUnavailable("模型返回的结构化输入不可用；本次调用已计入预算",
                                   reason=ModelFailureReason.TOOL_INPUT, tool_count=1, **diagnostic)
        return {"output": calls[0]["input"], "usage": parsed.get("usage", {}),
                "latency_seconds": round(time.monotonic() - started, 3), "model": self.model}
