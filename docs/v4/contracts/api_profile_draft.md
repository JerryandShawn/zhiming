# 画像查看与确认式编辑契约草稿 0.1.0

**草稿，未冻结、未实现。** 仅供主线采用；不注册路由、不修改现有服务。公共规则见 [公共契约](api_modules_common_draft.md)。所有错误响应使用公共 Error，HTTP 映射沿用公共错误表；每个端点允许的错误码列在 x-endpoints.errors。GET 的 request 表示规范化查询参数及路径外过滤条件，不是 GET body；路径 ID 使用公共 Id，subject_id 必须经服务端授权。

## 查看、确认和隐私

ProfileView按区返回条目、原话引用和待确认提案 ID；授权详情页可按引用获取原文，普通列表不内嵌出生原值、聊天正文或盘面私有材料。kind明确区分用户事实、偏好、未知和象征解释，不能将解释升级为事实。第七节解释为只读，不通过通用编辑写入；需P8对应写路径及主线明确采用。

ValueEdit针对单条可编辑结构化字段，confirmed 必须 true，new_value 必须实际出现在 user_quote 对应原文半开区间，引用修订必须当前有效；服务端精确核验，不能相信模型提示或客户端 source_ref。旧值/history、change_id/revision 与撤销引用保持，不能用通用对象批量赋值。R14显式变化信号、唯一旧候选、敏感分类同意按现有记忆服务判断：无明确变化的矛盾产生现有P3确认提案，pending_confirmation不是保存成功。原话缺失/歧义不猜字段；返回安全VALIDATION_ERROR或提问/待确认回执。

出生编辑先形成提案；未知精度禁止时间与不确定分钟数，大约精度要求时间及正整数不确定分钟数，精确时间不带误差。日期必须真实公历日期，时间HH:mm，真实时区/地点消歧由业务判断，不发新的模型请求。敏感变更先核当前分类用途同意，不能用一个 confirmed 勾选代替 consent_category 授权；确认提案须加载服务端当前值/来源，不接受模型自证。BirthData只出现在受保护编辑请求，禁止出现在普通ProfileView/日志/错误。

DeleteMemory明确 entry_only 与 source_segment，后者必须二次明确展示影响范围；服务器核验被删来源归属，并失效合并后代/历史值与派生引用。UndoChange按变更ID+修订，不用undo_token；遇后来编辑返回冲突而不是覆盖。所有成功提示来自程序回执，敏感确认一次规则由现有服务保存，不能因请求重试重复询问或重复写。

## 旧路由兼容待主线

现有 GET /api/subjects/self/profile 返回 effective/legacy_candidate/revision/requires_explicit_confirmation，POST /api/subjects/self/profile/confirm 已存在；本专题路径及Schema与旧格式不等价。保守方案是保留旧行为、主线显式适配或版本化采用新契约，不宣称旧路由已支持上述字段，不改 api_runtime_v1。

修订按端点表指定对象比较；确认加载当前 proposal revision，写成后回执实体可为画像/记忆；事务同时核依赖画像修订与来源。所有写遵守同ID同载荷、未知结果同ID回查、409保留草稿；source撤销410、同意缺失403，不能凭客户端 confirmed 越权。

## 端点映射（全部 draft）

| 方法与路径 | 请求 Schema | 成功响应 Schema | expected_revision 所属资源 |
| --- | --- | --- | --- |
| GET /api/subjects/{subject_id}/profile | ProfileQuery | ProfileView | none |
| POST /api/subjects/{subject_id}/profile/edits | ValueEdit | WriteResult | entry |
| POST /api/subjects/{subject_id}/profile/birth-proposals | BirthEdit | WriteResult | profile |
| POST /api/subjects/{subject_id}/profile/proposals/confirm | ConfirmProposal | WriteResult | proposal |
| POST /api/subjects/{subject_id}/memory/delete | DeleteMemory | WriteResult | entry |
| POST /api/subjects/{subject_id}/memory/undo | UndoChange | WriteResult | change |

Schema 使用 JSON Schema2020-12；公共引用只由测试本地 Registry 解析，禁止运行时联网取 Schema。x-examples 为公开合成正例，测试同时生成缺字段、越界、未知字段等反例。Schema 不能代替事务授权、当前来源核验、修订比较或幂等执行。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:mingjing:api:profile:draft:0.1.0",
  "$defs": {
    "ProfileQuery": {
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
        "space_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        }
      },
      "required": []
    },
    "Entry": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "section": {
          "type": "integer",
          "minimum": 1,
          "maximum": 8
        },
        "space_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "value": {
          "type": "string",
          "minLength": 1,
          "maxLength": 2000
        },
        "kind": {
          "enum": [
            "user_fact",
            "preference",
            "unknown",
            "symbolic"
          ]
        },
        "read_only": {
          "type": "boolean"
        },
        "source_refs": {
          "type": "array",
          "items": {
            "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/SourceRef"
          },
          "maxItems": 50,
          "minItems": 1
        },
        "change_id": {
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
        "id",
        "revision",
        "section",
        "space_id",
        "value",
        "kind",
        "read_only",
        "source_refs",
        "change_id"
      ],
      "allOf": [
        {
          "if": {
            "properties": {
              "section": {
                "const": 7
              }
            }
          },
          "then": {
            "properties": {
              "read_only": {
                "const": true
              }
            }
          }
        }
      ]
    },
    "ProfileView": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "subject_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "entries": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/Entry"
          },
          "maxItems": 100
        },
        "pending_proposal_ids": {
          "type": "array",
          "items": {
            "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
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
        "subject_id",
        "revision",
        "entries",
        "pending_proposal_ids",
        "next_cursor"
      ]
    },
    "ValueEdit": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "entry_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "new_value": {
          "type": "string",
          "minLength": 1,
          "maxLength": 2000
        },
        "confirmed": {
          "const": true,
          "type": "boolean"
        },
        "user_quote": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000
        },
        "source_ref": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/SourceRef"
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "entry_id",
        "new_value",
        "confirmed",
        "user_quote",
        "source_ref"
      ]
    },
    "BirthData": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "birth_date": {
          "type": "string",
          "format": "date"
        },
        "birth_time": {
          "type": [
            "string",
            "null"
          ],
          "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$"
        },
        "birth_place": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200
        },
        "gender": {
          "enum": [
            "male",
            "female",
            "unspecified"
          ]
        },
        "precision": {
          "enum": [
            "exact",
            "approximate",
            "unknown"
          ]
        },
        "uncertainty_minutes": {
          "type": [
            "integer",
            "null"
          ],
          "minimum": 1,
          "maximum": 1440
        }
      },
      "required": [
        "birth_date",
        "birth_time",
        "birth_place",
        "gender",
        "precision",
        "uncertainty_minutes"
      ],
      "allOf": [
        {
          "if": {
            "properties": {
              "precision": {
                "const": "unknown"
              }
            }
          },
          "then": {
            "properties": {
              "birth_time": {
                "type": "null"
              },
              "uncertainty_minutes": {
                "type": "null"
              }
            }
          },
          "else": {
            "properties": {
              "birth_time": {
                "type": "string"
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "precision": {
                "const": "approximate"
              }
            }
          },
          "then": {
            "properties": {
              "uncertainty_minutes": {
                "type": "integer"
              }
            }
          },
          "else": {
            "properties": {
              "uncertainty_minutes": {
                "type": "null"
              }
            }
          }
        }
      ]
    },
    "BirthEdit": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "data": {
          "$ref": "#/$defs/BirthData"
        },
        "confirmed": {
          "const": true,
          "type": "boolean"
        },
        "user_quote": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000
        },
        "source_ref": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/SourceRef"
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "data",
        "confirmed",
        "user_quote",
        "source_ref"
      ]
    },
    "ConfirmProposal": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "proposal_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "accepted": {
          "const": true,
          "type": "boolean"
        },
        "consent_category": {
          "enum": [
            "profile",
            "birth_data",
            "health",
            "finance",
            "relationships"
          ]
        },
        "user_quote": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000
        },
        "source_ref": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/SourceRef"
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "proposal_id",
        "accepted",
        "consent_category",
        "user_quote",
        "source_ref"
      ]
    },
    "DeleteMemory": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "entry_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "scope": {
          "enum": [
            "entry_only",
            "source_segment"
          ]
        },
        "confirmed": {
          "const": true,
          "type": "boolean"
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "entry_id",
        "scope",
        "confirmed"
      ]
    },
    "UndoChange": {
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
    "WriteResult": {
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
        "change_id": {
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
        "ok",
        "request_id",
        "receipt",
        "change_id"
      ],
      "allOf": [
        {
          "if": {
            "properties": {
              "receipt": {
                "properties": {
                  "write_status": {
                    "enum": [
                      "queued",
                      "pending_confirmation"
                    ]
                  }
                }
              }
            }
          },
          "then": {
            "properties": {
              "change_id": {
                "type": "null"
              }
            }
          },
          "else": {
            "properties": {
              "change_id": {
                "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
              }
            }
          }
        }
      ]
    }
  },
  "x-endpoints": [
    {
      "method": "GET",
      "path": "/api/subjects/{subject_id}/profile",
      "request": "ProfileQuery",
      "response": "ProfileView",
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
      "path": "/api/subjects/{subject_id}/profile/edits",
      "request": "ValueEdit",
      "response": "WriteResult",
      "revision_resource": "entry",
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
        "CONSENT_REQUIRED",
        "SOURCE_REVOKED"
      ]
    },
    {
      "method": "POST",
      "path": "/api/subjects/{subject_id}/profile/birth-proposals",
      "request": "BirthEdit",
      "response": "WriteResult",
      "revision_resource": "profile",
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
        "CONSENT_REQUIRED",
        "SOURCE_REVOKED"
      ]
    },
    {
      "method": "POST",
      "path": "/api/subjects/{subject_id}/profile/proposals/confirm",
      "request": "ConfirmProposal",
      "response": "WriteResult",
      "revision_resource": "proposal",
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
        "CONSENT_REQUIRED",
        "SOURCE_REVOKED"
      ]
    },
    {
      "method": "POST",
      "path": "/api/subjects/{subject_id}/memory/delete",
      "request": "DeleteMemory",
      "response": "WriteResult",
      "revision_resource": "entry",
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
        "CONSENT_REQUIRED",
        "SOURCE_REVOKED"
      ]
    },
    {
      "method": "POST",
      "path": "/api/subjects/{subject_id}/memory/undo",
      "request": "UndoChange",
      "response": "WriteResult",
      "revision_resource": "change",
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
        "CONSENT_REQUIRED",
        "SOURCE_REVOKED"
      ]
    }
  ],
  "x-examples": [
    {
      "schema": "ProfileQuery",
      "value": {}
    },
    {
      "schema": "ProfileView",
      "value": {
        "subject_id": "synthetic:s1",
        "revision": 1,
        "entries": [
          {
            "id": "synthetic:e1",
            "revision": 1,
            "section": 1,
            "space_id": "daily",
            "value": "合成偏好",
            "kind": "preference",
            "read_only": false,
            "source_refs": [
              {
                "message_id": "synthetic:m1",
                "revision": 1,
                "start": 0,
                "end": 2
              }
            ],
            "change_id": null
          }
        ],
        "pending_proposal_ids": [],
        "next_cursor": null
      }
    },
    {
      "schema": "ValueEdit",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 1,
        "entry_id": "synthetic:e1",
        "new_value": "合成",
        "confirmed": true,
        "user_quote": "合成",
        "source_ref": {
          "message_id": "synthetic:m1",
          "revision": 1,
          "start": 0,
          "end": 2
        }
      }
    },
    {
      "schema": "BirthEdit",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 1,
        "data": {
          "birth_date": "2000-01-01",
          "birth_time": null,
          "birth_place": "合成地点",
          "gender": "unspecified",
          "precision": "unknown",
          "uncertainty_minutes": null
        },
        "confirmed": true,
        "user_quote": "合成资料",
        "source_ref": {
          "message_id": "synthetic:m1",
          "revision": 1,
          "start": 0,
          "end": 2
        }
      }
    },
    {
      "schema": "ConfirmProposal",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 1,
        "proposal_id": "synthetic:p1",
        "accepted": true,
        "consent_category": "profile",
        "user_quote": "合成",
        "source_ref": {
          "message_id": "synthetic:m1",
          "revision": 1,
          "start": 0,
          "end": 2
        }
      }
    },
    {
      "schema": "DeleteMemory",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 1,
        "entry_id": "synthetic:e1",
        "scope": "entry_only",
        "confirmed": true
      }
    },
    {
      "schema": "UndoChange",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 1,
        "change_id": "synthetic:c1"
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
        },
        "change_id": "synthetic:c1"
      }
    }
  ]
}
```
