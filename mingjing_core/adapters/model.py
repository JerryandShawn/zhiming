"""Existing configured Anthropic-compatible provider, without tool orchestration."""
import json
import os
import time
import base64
import httpx
from ..domain.consultation import ModelUnavailable


class ConfiguredModel:
    def __init__(self, key=None, base=None, model=None):
        self.key = key if key is not None else os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY", "")
        self.base = (base or os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")).rstrip("/")
        self.model = model or os.getenv("KIMI_MODEL", "kimi-k3")

    def generate(self, *, system, payload, schema, purpose):
        if not self.key:
            raise ModelUnavailable("模型尚未配置；已保存的问题与固定牌阵可以恢复")
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
                "max_tokens": 14000 if purpose in ("synthesis", "repair") else 6000,
                "temperature": 1, "thinking": {"type": "enabled", "budget_tokens": 1024}}
        try:
            with httpx.Client(timeout=httpx.Timeout(240, connect=20), follow_redirects=False) as client:
                response = client.post(self.base + "/messages", headers=headers, json=body)
            if response.status_code != 200:
                raise ModelUnavailable(f"模型服务返回 HTTP {response.status_code}；本轮结果尚未提交")
            parsed = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelUnavailable("模型服务连接中断；调用预算已记录，可恢复同一请求") from exc
        if parsed.get("stop_reason") == "max_tokens":
            raise ModelUnavailable("模型输出超出本次上限；未展示未核验结果")
        calls = [c for c in parsed.get("content", []) if c.get("type") == "tool_use" and c.get("name") == "submit"]
        if len(calls) != 1 or not isinstance(calls[0].get("input"), dict):
            raise ModelUnavailable("模型未返回所需结构化结果；本次调用已计入预算")
        return {"output": calls[0]["input"], "usage": parsed.get("usage", {}),
                "latency_seconds": round(time.monotonic() - started, 3), "model": self.model}
