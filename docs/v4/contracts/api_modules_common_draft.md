# 模块API公共契约草稿 0.1.0

**状态：草稿，未冻结、未实现；仅供主线采用。** 不替换api_runtime_v1/线程运行、事件或core4信封。以下Schema为各专题的共同字段，格式JSON Schema2020-12，不能据Schema通过认定HTTP路由已存在。

认证沿用主线X-Token/将来的受保护cookie；cookie写请求须Origin/CSRF。owner只从认证解析，subject由已授权路径/过滤条件选择，资源不在当前授权范围统一404 SCOPE_NOT_FOUND，不泄露其他owner是否拥有资源。客户端禁止传owner/runtime/provider/lane、可信角色或来源状态。只投影经过当前来源/同意/撤销检查的数据；真实出生原值只在受保护资料编辑视图返回，不进入普通列表、日志或错误。

## 幂等和修订

所有写操作必须携带request_id和expected_revision；创建用0，修改用当前资源revision。事务中先核同owner+操作类型+request_id的原始载荷指纹，再核当前revision和授权来源。相同ID同载荷返回原回执且不重复副作用；相同ID改载荷409 IDEMPOTENCY_CONFLICT。模糊失败保留原ID和载荷，重试或回查原操作，禁止换新ID自动重试；unknown须先对账。不同业务操作才换ID。

409 REVISION_CONFLICT必须保留用户草稿，禁用保存，显示“内容已在别处更新，刷新后核对”，不得自动把expected_revision改成新值后重发。write_status来自程序回执，HTTP200或ok=true不代表已保存：queued/pending_confirmation只表示排队/待确认。主线可扩展具体资源响应，但不可由前端自行补造成功回执。

SourceRef的start/end为Unicode码点半开区间[start,end)，业务须另核start<end≤原文长度、精确原话、message revision与owner/subject授权；JSON Schema无法独自验证原话或PG当前状态。

## 错误和HTTP映射

| HTTP | code | 客户端行为 |
| --- | --- | --- |
| 400/422 | VALIDATION_ERROR | 保留输入、显示字段错误；不显示私有正文 |
| 401/403 | UNAUTHORIZED / FORBIDDEN | 登录或取得当前用途授权，不猜owner |
| 404 | SCOPE_NOT_FOUND | 不暴露其他owner资源 |
| 409 | REVISION_CONFLICT / IDEMPOTENCY_CONFLICT / REVIEW_PLAN_CHANGED | 保留草稿，重新核对/审阅，不盲重提 |
| 410 | SOURCE_REVOKED / REVIEW_EXPIRED | 失效项不可继续采用 |
| 403/409 | CONSENT_REQUIRED / REVIEW_REQUIRED / QUALITY_GATE_CLOSED | 显式同意或审阅，不绕过旧Q5门 |
| 429 | RATE_LIMITED | 同ID按Retry-After重试，不能增加业务操作 |
| 503 | UNKNOWN_RESULT | 同ID回查/对账，不能据超时断言未发生 |
| 501 | DRAFT_NOT_IMPLEMENTED | 草稿能力尚未接线，不假回成功 |

## 公共Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:mingjing:api:common:draft:0.1.0",
  "$defs": {
    "Id": {
      "type": "string",
      "minLength": 1,
      "maxLength": 128,
      "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    },
    "Revision": {
      "type": "integer",
      "minimum": 1,
      "maximum": 9007199254740991
    },
    "WriteIdentity": {
      "type": "object",
      "required": [
        "request_id",
        "expected_revision"
      ],
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "#/$defs/Id"
        },
        "expected_revision": {
          "type": "integer",
          "minimum": 0,
          "maximum": 9007199254740991
        }
      }
    },
    "SourceRef": {
      "type": "object",
      "required": [
        "message_id",
        "revision",
        "start",
        "end"
      ],
      "additionalProperties": false,
      "properties": {
        "message_id": {
          "$ref": "#/$defs/Id"
        },
        "revision": {
          "$ref": "#/$defs/Revision"
        },
        "start": {
          "type": "integer",
          "minimum": 0
        },
        "end": {
          "type": "integer",
          "minimum": 1
        }
      }
    },
    "Receipt": {
      "type": "object",
      "required": [
        "operation_id",
        "write_status",
        "entity_id",
        "revision"
      ],
      "additionalProperties": false,
      "properties": {
        "operation_id": {
          "$ref": "#/$defs/Id"
        },
        "write_status": {
          "enum": [
            "saved",
            "updated",
            "deleted",
            "undone",
            "skipped",
            "pending_confirmation",
            "queued"
          ]
        },
        "entity_id": {
          "$ref": "#/$defs/Id"
        },
        "revision": {
          "$ref": "#/$defs/Revision"
        }
      }
    },
    "WriteResult": {
      "type": "object",
      "required": [
        "ok",
        "request_id",
        "receipt"
      ],
      "additionalProperties": false,
      "properties": {
        "ok": {
          "const": true
        },
        "request_id": {
          "$ref": "#/$defs/Id"
        },
        "receipt": {
          "$ref": "#/$defs/Receipt"
        }
      }
    },
    "Error": {
      "type": "object",
      "required": [
        "ok",
        "error"
      ],
      "additionalProperties": false,
      "properties": {
        "ok": {
          "const": false
        },
        "request_id": {
          "$ref": "#/$defs/Id"
        },
        "error": {
          "type": "object",
          "required": [
            "code",
            "message",
            "retryable"
          ],
          "additionalProperties": false,
          "properties": {
            "code": {
              "enum": [
                "UNAUTHORIZED",
                "FORBIDDEN",
                "SCOPE_NOT_FOUND",
                "VALIDATION_ERROR",
                "REVISION_CONFLICT",
                "IDEMPOTENCY_CONFLICT",
                "CONSENT_REQUIRED",
                "SOURCE_REVOKED",
                "REVIEW_REQUIRED",
                "REVIEW_EXPIRED",
                "REVIEW_PLAN_CHANGED",
                "QUALITY_GATE_CLOSED",
                "UNKNOWN_RESULT",
                "RATE_LIMITED",
                "DRAFT_NOT_IMPLEMENTED"
              ]
            },
            "message": {
              "type": "string",
              "minLength": 1,
              "maxLength": 300
            },
            "retryable": {
              "type": "boolean"
            },
            "current_revision": {
              "$ref": "#/$defs/Revision"
            }
          }
        }
      }
    }
  }
}
```
