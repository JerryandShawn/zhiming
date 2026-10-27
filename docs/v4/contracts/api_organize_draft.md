# 旧对话整理接口契约草稿 0.1.0

**草稿，未冻结、未实现。** 仅供主线采用；不注册路由、不修改现有服务。公共规则见 [公共契约](api_modules_common_draft.md)。所有错误响应使用公共 Error，HTTP 映射沿用公共错误表；每个端点允许的错误码列在 x-endpoints.errors。GET 的 request 表示规范化查询参数及路径外过滤条件，不是 GET body；路径 ID 使用公共 Id，subject_id 必须经服务端授权。

## 审阅、应用和撤销

建议→用户编辑→当前精确计划预览→用户明确 accepted=true→服务端签发审阅凭证→应用→字段精确撤销。建议只读派生摘要，禁止改变聊天正文。建议创建是 request_id 幂等的排队操作，WriteResult 为 queued 时不表示已整理。编辑含改名/合并/拆分/移动/忽略，均改变 batch revision 和计划指纹，旧审阅立即失效。rename的title为1至80字；merge的target_ids是至少两个不同话题且同区，target_id必须在集合中；split用message_ids选原话题的真子集并提供title（不是新话题ID列表）；move只换区，ignore保留原文。topic预览附消息ID、时间跨度、短样例摘要、置信度、待审清单和降级说明；敏感摘要仍按当前用途授权过滤。现有纯模块move只认默认区，自建区须主线适配后采用，禁止文档假称已支持。target_ids 的实际集合、分拆互斥与来源完整性由业务核验，不能凭模型文字执行。

审阅 fingerprint 是服务端对当前完整 ChangeSet 的规范化摘要，不是客户端任意描述的 hash。review 响应只在用户认证、当前来源授权及精确预览均核对后签发；模型不能自我批准。服务端存储 receipt_id 对 owner/subject/batch/revision/fingerprint/accepted/时间的绑定。凭证有效期24小时，不接受未来 reviewed_at；expires_at必须等于reviewed_at+24小时，由服务端时钟决定，不从客户端取值；过期410 REVIEW_EXPIRED，计划变动409 REVIEW_PLAN_CHANGED，未审阅409 REVIEW_REQUIRED。应用只收凭证 ID，不能收客户端 owner/accepted/reviewed_at 冒充权威。应用事务重新加载凭证、重算计划、核来源与修订；凭证只消费一次，同 request_id 返回原回执。

保留 P5b review_gate 的 additive-only：只补空/缺失标签和新话题元数据，不覆盖现存非空标签，不能删除原文。应用账本区分字段不存在与显式 null；撤销按 change_id + expected_revision，准确恢复缺失/null/旧值，遇后续编辑不覆盖，回执 skipped 或部分 undone 并返回元数据 conflicts，不带正文/旧隐私值。来源撤销同时使依赖摘要与未应用计划失效。

旧Q5 blind B 冻结、旧组合质量门失败不改。quality_gate=record_only 表示仅建议和人工审阅能力，绝不据草稿开启真实历史自动应用；未解除应用门时返回409 QUALITY_GATE_CLOSED，即使有审阅也不可绕过。手工逐计划应用仍需主线在本地/产品授权边界明确接线；本草稿不发真实历史操作。保留 /api/organize/apply 与 /revert 原设计意图；此处显式 batch 路径是候选形式，由主线兼容采用，未替换任何既有路由。

所有写同 ID 同载荷回原回执；未知结果503 UNKNOWN_RESULT须同ID对账；409保留编辑草稿。读取必须重新检查源范围与同意，不泄露撤销正文。

## 端点映射（全部 draft）

| 方法与路径 | 请求 Schema | 成功响应 Schema | expected_revision 所属资源 |
| --- | --- | --- | --- |
| GET /api/organize/proposal | ProposalQuery | ProposalList | none |
| POST /api/organize/proposal | Suggest | WriteResult | new batch (0) |
| PATCH /api/organize/{batch_id} | Edit | WriteResult | batch |
| POST /api/organize/{batch_id}/review | Review | ReviewResult | batch |
| POST /api/organize/apply/{batch_id} | Apply | ApplyResult | batch |
| POST /api/organize/revert/{batch_id} | Revert | RevertResult | changeset |

Schema 使用 JSON Schema2020-12；公共引用只由测试本地 Registry 解析，禁止运行时联网取 Schema。x-examples 为公开合成正例，测试同时生成缺字段、越界、未知字段等反例。Schema 不能代替事务授权、当前来源核验、修订比较或幂等执行。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:mingjing:api:organize:draft:0.1.0",
  "$defs": {
    "ProposalQuery": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "limit": {
          "type": "integer",
          "minimum": 1,
          "maximum": 100
        },
        "cursor": {
          "type": "string",
          "minLength": 1,
          "maxLength": 512
        },
        "subject_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "batch_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        }
      },
      "required": []
    },
    "Suggest": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "const": 0,
          "type": "integer"
        },
        "subject_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "source_refs": {
          "type": "array",
          "items": {
            "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/SourceRef"
          },
          "maxItems": 50,
          "minItems": 1
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "subject_id",
        "source_refs"
      ]
    },
    "PlanEdit": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "kind": {
          "enum": [
            "rename",
            "merge",
            "split",
            "move",
            "ignore"
          ]
        },
        "target_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "title": {
          "type": "string",
          "minLength": 1,
          "maxLength": 80
        },
        "target_ids": {
          "type": "array",
          "items": {
            "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
          },
          "maxItems": 100,
          "minItems": 2,
          "uniqueItems": true
        },
        "message_ids": {
          "type": "array",
          "items": {
            "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
          },
          "maxItems": 100,
          "minItems": 1,
          "uniqueItems": true
        },
        "space_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        }
      },
      "required": [
        "kind",
        "target_id"
      ],
      "allOf": [
        {
          "if": {
            "properties": {
              "kind": {
                "const": "rename"
              }
            }
          },
          "then": {
            "required": [
              "title"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "kind": {
                "const": "merge"
              }
            }
          },
          "then": {
            "required": [
              "target_ids"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "kind": {
                "const": "split"
              }
            }
          },
          "then": {
            "required": [
              "message_ids",
              "title"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "kind": {
                "const": "move"
              }
            }
          },
          "then": {
            "required": [
              "space_id"
            ]
          }
        },
        {
          "if": {
            "properties": {
              "kind": {
                "const": "rename"
              }
            }
          },
          "then": {
            "properties": {
              "target_ids": false,
              "message_ids": false,
              "space_id": false
            }
          }
        },
        {
          "if": {
            "properties": {
              "kind": {
                "const": "merge"
              }
            }
          },
          "then": {
            "properties": {
              "message_ids": false,
              "space_id": false
            }
          }
        },
        {
          "if": {
            "properties": {
              "kind": {
                "const": "split"
              }
            }
          },
          "then": {
            "properties": {
              "target_ids": false,
              "space_id": false
            }
          }
        },
        {
          "if": {
            "properties": {
              "kind": {
                "const": "move"
              }
            }
          },
          "then": {
            "properties": {
              "title": false,
              "target_ids": false,
              "message_ids": false
            }
          }
        },
        {
          "if": {
            "properties": {
              "kind": {
                "const": "ignore"
              }
            }
          },
          "then": {
            "properties": {
              "title": false,
              "target_ids": false,
              "message_ids": false,
              "space_id": false
            }
          }
        }
      ]
    },
    "Edit": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "edits": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/PlanEdit"
          },
          "maxItems": 100,
          "minItems": 1
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "edits"
      ]
    },
    "Review": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "plan_fingerprint": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        "accepted": {
          "const": true,
          "type": "boolean"
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "plan_fingerprint",
        "accepted"
      ]
    },
    "Apply": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "plan_fingerprint": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        "review_receipt_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "plan_fingerprint",
        "review_receipt_id"
      ]
    },
    "Revert": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "change_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "change_id"
      ]
    },
    "Proposal": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "batch_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "subject_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "plan_fingerprint": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        "status": {
          "enum": [
            "proposed",
            "reviewed",
            "applied",
            "reverted",
            "invalidated"
          ]
        },
        "quality_gate": {
          "const": "record_only"
        },
        "source_refs": {
          "type": "array",
          "items": {
            "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/SourceRef"
          },
          "maxItems": 50,
          "minItems": 1
        },
        "topics": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/SuggestedTopic"
          },
          "maxItems": 100
        },
        "needs_review": {
          "type": "array",
          "items": {
            "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
          },
          "maxItems": 100
        },
        "ignored_count": {
          "type": "integer",
          "minimum": 0
        },
        "encoder_mode": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "degradation": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 200
        }
      },
      "required": [
        "batch_id",
        "subject_id",
        "revision",
        "plan_fingerprint",
        "status",
        "quality_gate",
        "source_refs",
        "topics",
        "needs_review",
        "ignored_count",
        "encoder_mode",
        "degradation"
      ]
    },
    "SuggestedTopic": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "space_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "title": {
          "type": "string",
          "minLength": 1,
          "maxLength": 80
        },
        "message_ids": {
          "type": "array",
          "items": {
            "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
          },
          "maxItems": 100
        },
        "start_at": {
          "type": "string",
          "format": "date-time",
          "pattern": "(Z|[+-]\\d\\d:\\d\\d)$"
        },
        "end_at": {
          "type": "string",
          "format": "date-time",
          "pattern": "(Z|[+-]\\d\\d:\\d\\d)$"
        },
        "sample": {
          "type": "string",
          "maxLength": 80
        },
        "confidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "source_refs": {
          "type": "array",
          "items": {
            "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/SourceRef"
          },
          "maxItems": 50,
          "minItems": 1
        }
      },
      "required": [
        "id",
        "space_id",
        "title",
        "message_ids",
        "start_at",
        "end_at",
        "sample",
        "confidence",
        "source_refs"
      ]
    },
    "ProposalList": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/Proposal"
          },
          "maxItems": 100
        },
        "next_cursor": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 512
        }
      },
      "required": [
        "items",
        "next_cursor"
      ]
    },
    "ReviewResult": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "ok": {
          "const": true
        },
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "receipt": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Receipt"
        },
        "review": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "receipt_id": {
              "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
            },
            "batch_id": {
              "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
            },
            "revision": {
              "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
            },
            "plan_fingerprint": {
              "type": "string",
              "pattern": "^[a-f0-9]{64}$"
            },
            "reviewed_at": {
              "type": "string",
              "format": "date-time",
              "pattern": "(Z|[+-]\\d\\d:\\d\\d)$"
            },
            "expires_at": {
              "type": "string",
              "format": "date-time",
              "pattern": "(Z|[+-]\\d\\d:\\d\\d)$"
            }
          },
          "required": [
            "receipt_id",
            "batch_id",
            "revision",
            "plan_fingerprint",
            "reviewed_at",
            "expires_at"
          ]
        }
      },
      "required": [
        "ok",
        "request_id",
        "receipt",
        "review"
      ]
    },
    "WriteResult": {
      "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/WriteResult"
    },
    "ApplyResult": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "ok": {
          "const": true
        },
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "receipt": {
          "allOf": [
            {
              "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Receipt"
            },
            {
              "properties": {
                "write_status": {
                  "enum": [
                    "saved",
                    "updated"
                  ]
                }
              }
            }
          ]
        },
        "change_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        }
      },
      "required": [
        "ok",
        "request_id",
        "receipt",
        "change_id"
      ]
    },
    "RevertResult": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "ok": {
          "const": true
        },
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "receipt": {
          "allOf": [
            {
              "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Receipt"
            },
            {
              "properties": {
                "write_status": {
                  "enum": [
                    "undone",
                    "skipped"
                  ]
                }
              }
            }
          ]
        },
        "restored_count": {
          "type": "integer",
          "minimum": 0
        },
        "conflicts": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "entity_id": {
                "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
              },
              "field": {
                "enum": [
                  "space_id",
                  "topic_id",
                  "title",
                  "status",
                  "space_secondary",
                  "route_source",
                  "route_confidence"
                ]
              },
              "reason": {
                "enum": [
                  "later_edit",
                  "source_revoked",
                  "scope_changed"
                ]
              }
            },
            "required": [
              "entity_id",
              "field",
              "reason"
            ]
          },
          "maxItems": 100
        }
      },
      "required": [
        "ok",
        "request_id",
        "receipt",
        "restored_count",
        "conflicts"
      ]
    }
  },
  "x-endpoints": [
    {
      "method": "GET",
      "path": "/api/organize/proposal",
      "request": "ProposalQuery",
      "response": "ProposalList",
      "revision_resource": "none",
      "errors": [
        "UNAUTHORIZED",
        "FORBIDDEN",
        "SCOPE_NOT_FOUND",
        "VALIDATION_ERROR",
        "DRAFT_NOT_IMPLEMENTED",
        "CONSENT_REQUIRED",
        "SOURCE_REVOKED"
      ]
    },
    {
      "method": "POST",
      "path": "/api/organize/proposal",
      "request": "Suggest",
      "response": "WriteResult",
      "revision_resource": "new batch (0)",
      "errors": [
        "UNAUTHORIZED",
        "FORBIDDEN",
        "SCOPE_NOT_FOUND",
        "VALIDATION_ERROR",
        "DRAFT_NOT_IMPLEMENTED",
        "REVISION_CONFLICT",
        "IDEMPOTENCY_CONFLICT",
        "UNKNOWN_RESULT",
        "RATE_LIMITED",
        "CONSENT_REQUIRED",
        "SOURCE_REVOKED",
        "REVIEW_REQUIRED",
        "REVIEW_EXPIRED",
        "REVIEW_PLAN_CHANGED",
        "QUALITY_GATE_CLOSED",
        "SOURCE_REVOKED",
        "CONSENT_REQUIRED"
      ]
    },
    {
      "method": "PATCH",
      "path": "/api/organize/{batch_id}",
      "request": "Edit",
      "response": "WriteResult",
      "revision_resource": "batch",
      "errors": [
        "UNAUTHORIZED",
        "FORBIDDEN",
        "SCOPE_NOT_FOUND",
        "VALIDATION_ERROR",
        "DRAFT_NOT_IMPLEMENTED",
        "REVISION_CONFLICT",
        "IDEMPOTENCY_CONFLICT",
        "UNKNOWN_RESULT",
        "RATE_LIMITED",
        "CONSENT_REQUIRED",
        "SOURCE_REVOKED",
        "REVIEW_REQUIRED",
        "REVIEW_EXPIRED",
        "REVIEW_PLAN_CHANGED",
        "QUALITY_GATE_CLOSED",
        "SOURCE_REVOKED",
        "CONSENT_REQUIRED"
      ]
    },
    {
      "method": "POST",
      "path": "/api/organize/{batch_id}/review",
      "request": "Review",
      "response": "ReviewResult",
      "revision_resource": "batch",
      "errors": [
        "UNAUTHORIZED",
        "FORBIDDEN",
        "SCOPE_NOT_FOUND",
        "VALIDATION_ERROR",
        "DRAFT_NOT_IMPLEMENTED",
        "REVISION_CONFLICT",
        "IDEMPOTENCY_CONFLICT",
        "UNKNOWN_RESULT",
        "RATE_LIMITED",
        "CONSENT_REQUIRED",
        "SOURCE_REVOKED",
        "REVIEW_REQUIRED",
        "REVIEW_EXPIRED",
        "REVIEW_PLAN_CHANGED",
        "QUALITY_GATE_CLOSED",
        "SOURCE_REVOKED",
        "CONSENT_REQUIRED"
      ]
    },
    {
      "method": "POST",
      "path": "/api/organize/apply/{batch_id}",
      "request": "Apply",
      "response": "ApplyResult",
      "revision_resource": "batch",
      "errors": [
        "UNAUTHORIZED",
        "FORBIDDEN",
        "SCOPE_NOT_FOUND",
        "VALIDATION_ERROR",
        "DRAFT_NOT_IMPLEMENTED",
        "REVISION_CONFLICT",
        "IDEMPOTENCY_CONFLICT",
        "UNKNOWN_RESULT",
        "RATE_LIMITED",
        "CONSENT_REQUIRED",
        "SOURCE_REVOKED",
        "REVIEW_REQUIRED",
        "REVIEW_EXPIRED",
        "REVIEW_PLAN_CHANGED",
        "QUALITY_GATE_CLOSED",
        "SOURCE_REVOKED",
        "CONSENT_REQUIRED"
      ]
    },
    {
      "method": "POST",
      "path": "/api/organize/revert/{batch_id}",
      "request": "Revert",
      "response": "RevertResult",
      "revision_resource": "changeset",
      "errors": [
        "UNAUTHORIZED",
        "FORBIDDEN",
        "SCOPE_NOT_FOUND",
        "VALIDATION_ERROR",
        "DRAFT_NOT_IMPLEMENTED",
        "REVISION_CONFLICT",
        "IDEMPOTENCY_CONFLICT",
        "UNKNOWN_RESULT",
        "RATE_LIMITED",
        "CONSENT_REQUIRED",
        "SOURCE_REVOKED",
        "REVIEW_REQUIRED",
        "REVIEW_EXPIRED",
        "REVIEW_PLAN_CHANGED",
        "QUALITY_GATE_CLOSED",
        "SOURCE_REVOKED",
        "CONSENT_REQUIRED"
      ]
    }
  ],
  "x-examples": [
    {
      "schema": "ProposalQuery",
      "value": {}
    },
    {
      "schema": "Suggest",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 0,
        "subject_id": "synthetic:s1",
        "source_refs": [
          {
            "message_id": "synthetic:m1",
            "revision": 1,
            "start": 0,
            "end": 2
          }
        ]
      }
    },
    {
      "schema": "Edit",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 1,
        "edits": [
          {
            "kind": "rename",
            "target_id": "synthetic:t1",
            "title": "合成标题"
          }
        ]
      }
    },
    {
      "schema": "Review",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 1,
        "plan_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "accepted": true
      }
    },
    {
      "schema": "Apply",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 2,
        "plan_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "review_receipt_id": "synthetic:review1"
      }
    },
    {
      "schema": "Revert",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 3,
        "change_id": "synthetic:change1"
      }
    },
    {
      "schema": "ProposalList",
      "value": {
        "items": [
          {
            "batch_id": "synthetic:b1",
            "subject_id": "synthetic:s1",
            "revision": 1,
            "plan_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "status": "proposed",
            "quality_gate": "record_only",
            "source_refs": [
              {
                "message_id": "synthetic:m1",
                "revision": 1,
                "start": 0,
                "end": 2
              }
            ],
            "topics": [
              {
                "id": "synthetic:t1",
                "space_id": "daily",
                "title": "合成话题",
                "message_ids": [
                  "synthetic:m1"
                ],
                "start_at": "2026-10-27T17:00:00+08:00",
                "end_at": "2026-10-27T17:00:00+08:00",
                "sample": "合成摘要",
                "confidence": 0.6,
                "source_refs": [
                  {
                    "message_id": "synthetic:m1",
                    "revision": 1,
                    "start": 0,
                    "end": 2
                  }
                ]
              }
            ],
            "needs_review": [
              "synthetic:t1"
            ],
            "ignored_count": 0,
            "encoder_mode": "synthetic",
            "degradation": null
          }
        ],
        "next_cursor": null
      }
    },
    {
      "schema": "ReviewResult",
      "value": {
        "ok": true,
        "request_id": "synthetic:r1",
        "receipt": {
          "operation_id": "synthetic:op1",
          "entity_id": "synthetic:e1",
          "revision": 2,
          "write_status": "updated"
        },
        "review": {
          "receipt_id": "synthetic:review1",
          "batch_id": "synthetic:b1",
          "revision": 2,
          "plan_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "reviewed_at": "2026-10-27T17:00:00+08:00",
          "expires_at": "2026-10-28T17:00:00+08:00"
        }
      }
    },
    {
      "schema": "ApplyResult",
      "value": {
        "ok": true,
        "request_id": "synthetic:r1",
        "receipt": {
          "operation_id": "synthetic:op1",
          "entity_id": "synthetic:e1",
          "revision": 2,
          "write_status": "updated"
        },
        "change_id": "synthetic:change1"
      }
    },
    {
      "schema": "RevertResult",
      "value": {
        "ok": true,
        "request_id": "synthetic:r1",
        "receipt": {
          "operation_id": "synthetic:op1",
          "entity_id": "synthetic:e1",
          "revision": 2,
          "write_status": "undone"
        },
        "restored_count": 1,
        "conflicts": []
      }
    },
    {
      "schema": "WriteResult",
      "value": {
        "ok": true,
        "request_id": "synthetic:r1",
        "receipt": {
          "operation_id": "synthetic:op1",
          "entity_id": "synthetic:e1",
          "revision": 2,
          "write_status": "updated"
        }
      }
    }
  ]
}
```
