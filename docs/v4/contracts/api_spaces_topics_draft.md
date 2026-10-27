# 区与话题接口契约草稿 0.1.0

**草稿，未冻结、未实现。** 仅供主线采用；不注册路由、不修改现有服务。公共规则见 [公共契约](api_modules_common_draft.md)。所有错误响应使用公共 Error，HTTP 映射沿用公共错误表；每个端点允许的错误码列在 x-endpoints.errors。GET 的 request 表示规范化查询参数及路径外过滤条件，不是 GET body；路径 ID 使用公共 Id，subject_id 必须经服务端授权。

## 语义和兼容

默认七区 daily/career/relationships/family/wellbeing/finance/metaphysics 只是初始数据，不能把区 ID 限死为枚举；允许用户自建区。敏感区的读取与写入仍逐次核验当前用途同意，hidden 只是显示偏好，不是授权。sensitive 在创建时指定，后续降级不得通过普通改名接口绕过同意，另由主线采用现有隐私流程。

列表按稳定 order、id 排序；cursor 绑定 owner、subject、过滤条件及快照，不能跨区/跨主体复用。路径 space_id 是话题创建/列表唯一目标；重复查询参数不得改变该归属。修改 topic 的 space_id 是移动，不复制/删除原始消息；消息 route 只更改标签，topic 必须属于所选区，拒绝客户端 score、source_text、owner。

保守兼容方案：保留现有 /api/cases*，话题 status=case 必须携带可授权的 case_id，其他状态 case_id=null；二者通过显式引用关联，不假设迁移或替换事项。space_secondary最多一个且不得等于主区，手工路由由服务端标 route_source=user、可信置信度，客户端不可指定；topic_id=null表示尚无话题，不自动制造新话题。最后活跃14天后归档是主线运行策略，本草稿不改调度。summary_until_message_id界定摘要覆盖上界，created_at≤last_at，服务端按瞬时比较；summary 是带版本来源的派生视图，来源撤销后失效重算，不作为独立用户事实。归档/隐藏/移动不删消息、记忆或历史。

所有修改遵守公共同 ID 同载荷回执与 409 保留草稿规则；业务事务核验目标区/话题当前权限和 revision，不因 Schema 接受 ID 就放行。来源失效返回410 SOURCE_REVOKED，缺用途同意403 CONSENT_REQUIRED；这两码适用于相关读写。

## 端点映射（全部 draft）

| 方法与路径 | 请求 Schema | 成功响应 Schema | expected_revision 所属资源 |
| --- | --- | --- | --- |
| GET /api/spaces | ListQuery | SpaceList | none |
| POST /api/spaces | CreateSpace | WriteResult | new space (0) |
| PATCH /api/spaces/{space_id} | PatchSpace | WriteResult | space |
| GET /api/spaces/{space_id}/topics | ListQuery | TopicList | none |
| POST /api/spaces/{space_id}/topics | CreateTopic | WriteResult | new topic (0) |
| PATCH /api/topics/{topic_id} | PatchTopic | WriteResult | topic |
| POST /api/messages/{message_id}/route | RouteMessage | WriteResult | message |

Schema 使用 JSON Schema2020-12；公共引用只由测试本地 Registry 解析，禁止运行时联网取 Schema。x-examples 为公开合成正例，测试同时生成缺字段、越界、未知字段等反例。Schema 不能代替事务授权、当前来源核验、修订比较或幂等执行。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:mingjing:api:spaces_topics:draft:0.1.0",
  "$defs": {
    "ListQuery": {
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
        "include_hidden": {
          "type": "boolean"
        }
      },
      "required": []
    },
    "Space": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "name": {
          "type": "string",
          "minLength": 1,
          "maxLength": 60
        },
        "description": {
          "type": "string",
          "maxLength": 500
        },
        "order": {
          "type": "integer",
          "minimum": 0,
          "maximum": 10000
        },
        "hidden": {
          "type": "boolean"
        },
        "sensitive": {
          "type": "boolean"
        }
      },
      "required": [
        "id",
        "revision",
        "name",
        "description",
        "order",
        "hidden",
        "sensitive"
      ]
    },
    "SpaceList": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/Space"
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
    "CreateSpace": {
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
        "name": {
          "type": "string",
          "minLength": 1,
          "maxLength": 60
        },
        "description": {
          "type": "string",
          "maxLength": 500
        },
        "sensitive": {
          "type": "boolean"
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "name",
        "description",
        "sensitive"
      ]
    },
    "PatchSpace": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "patch": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "name": {
              "type": "string",
              "minLength": 1,
              "maxLength": 60
            },
            "description": {
              "type": "string",
              "maxLength": 500
            },
            "order": {
              "type": "integer",
              "minimum": 0,
              "maximum": 10000
            },
            "hidden": {
              "type": "boolean"
            }
          },
          "required": [],
          "minProperties": 1
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "patch"
      ]
    },
    "Topic": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "space_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "title": {
          "type": "string",
          "minLength": 1,
          "maxLength": 80
        },
        "status": {
          "enum": [
            "open",
            "archived",
            "case"
          ]
        },
        "summary": {
          "type": "string",
          "maxLength": 1000
        },
        "source_refs": {
          "type": "array",
          "items": {
            "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/SourceRef"
          },
          "maxItems": 50
        },
        "case_id": {
          "anyOf": [
            {
              "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
            },
            {
              "type": "null"
            }
          ]
        },
        "updated_at": {
          "type": "string",
          "format": "date-time",
          "pattern": "(Z|[+-]\\d\\d:\\d\\d)$"
        },
        "summary_until_message_id": {
          "anyOf": [
            {
              "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
            },
            {
              "type": "null"
            }
          ]
        },
        "created_at": {
          "type": "string",
          "format": "date-time",
          "pattern": "(Z|[+-]\\d\\d:\\d\\d)$"
        },
        "last_at": {
          "type": "string",
          "format": "date-time",
          "pattern": "(Z|[+-]\\d\\d:\\d\\d)$"
        }
      },
      "required": [
        "id",
        "space_id",
        "revision",
        "title",
        "status",
        "summary",
        "source_refs",
        "case_id",
        "updated_at",
        "summary_until_message_id",
        "created_at",
        "last_at"
      ],
      "allOf": [
        {
          "if": {
            "properties": {
              "status": {
                "const": "case"
              }
            }
          },
          "then": {
            "properties": {
              "case_id": {
                "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
              }
            }
          },
          "else": {
            "properties": {
              "case_id": {
                "type": "null"
              }
            }
          }
        }
      ]
    },
    "TopicList": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/Topic"
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
    "CreateTopic": {
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
        "title": {
          "type": "string",
          "minLength": 1,
          "maxLength": 80
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "title"
      ]
    },
    "PatchTopic": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "patch": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "title": {
              "type": "string",
              "minLength": 1,
              "maxLength": 80
            },
            "space_id": {
              "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
            },
            "status": {
              "enum": [
                "open",
                "archived",
                "case"
              ]
            },
            "case_id": {
              "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
            }
          },
          "required": [],
          "minProperties": 1,
          "allOf": [
            {
              "if": {
                "required": [
                  "status"
                ],
                "properties": {
                  "status": {
                    "const": "case"
                  }
                }
              },
              "then": {
                "required": [
                  "case_id"
                ]
              }
            }
          ]
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "patch"
      ]
    },
    "RouteMessage": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "space_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "topic_id": {
          "anyOf": [
            {
              "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
            },
            {
              "type": "null"
            }
          ]
        },
        "space_secondary": {
          "anyOf": [
            {
              "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
            },
            {
              "type": "null"
            }
          ]
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "space_id",
        "topic_id",
        "space_secondary"
      ]
    },
    "WriteResult": {
      "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/WriteResult"
    }
  },
  "x-endpoints": [
    {
      "method": "GET",
      "path": "/api/spaces",
      "request": "ListQuery",
      "response": "SpaceList",
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
      "path": "/api/spaces",
      "request": "CreateSpace",
      "response": "WriteResult",
      "revision_resource": "new space (0)",
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
        "SOURCE_REVOKED"
      ]
    },
    {
      "method": "PATCH",
      "path": "/api/spaces/{space_id}",
      "request": "PatchSpace",
      "response": "WriteResult",
      "revision_resource": "space",
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
        "SOURCE_REVOKED"
      ]
    },
    {
      "method": "GET",
      "path": "/api/spaces/{space_id}/topics",
      "request": "ListQuery",
      "response": "TopicList",
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
      "path": "/api/spaces/{space_id}/topics",
      "request": "CreateTopic",
      "response": "WriteResult",
      "revision_resource": "new topic (0)",
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
        "SOURCE_REVOKED"
      ]
    },
    {
      "method": "PATCH",
      "path": "/api/topics/{topic_id}",
      "request": "PatchTopic",
      "response": "WriteResult",
      "revision_resource": "topic",
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
        "SOURCE_REVOKED"
      ]
    },
    {
      "method": "POST",
      "path": "/api/messages/{message_id}/route",
      "request": "RouteMessage",
      "response": "WriteResult",
      "revision_resource": "message",
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
        "SOURCE_REVOKED"
      ]
    }
  ],
  "x-examples": [
    {
      "schema": "ListQuery",
      "value": {}
    },
    {
      "schema": "CreateSpace",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 0,
        "name": "合成区",
        "description": "",
        "sensitive": false
      }
    },
    {
      "schema": "PatchSpace",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 1,
        "patch": {
          "hidden": true
        }
      }
    },
    {
      "schema": "CreateTopic",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 0,
        "title": "合成话题"
      }
    },
    {
      "schema": "PatchTopic",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 1,
        "patch": {
          "status": "archived"
        }
      }
    },
    {
      "schema": "RouteMessage",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 1,
        "space_id": "daily",
        "topic_id": null,
        "space_secondary": null
      }
    },
    {
      "schema": "SpaceList",
      "value": {
        "items": [
          {
            "id": "daily",
            "revision": 1,
            "name": "日常",
            "description": "",
            "order": 0,
            "hidden": false,
            "sensitive": false
          }
        ],
        "next_cursor": null
      }
    },
    {
      "schema": "TopicList",
      "value": {
        "items": [
          {
            "id": "synthetic:t1",
            "space_id": "daily",
            "revision": 1,
            "title": "合成话题",
            "status": "open",
            "summary": "",
            "source_refs": [
              {
                "message_id": "synthetic:m1",
                "revision": 1,
                "start": 0,
                "end": 2
              }
            ],
            "case_id": null,
            "updated_at": "2026-10-27T17:00:00+08:00",
            "summary_until_message_id": null,
            "created_at": "2026-10-27T17:00:00+08:00",
            "last_at": "2026-10-27T17:00:00+08:00"
          }
        ],
        "next_cursor": null
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
