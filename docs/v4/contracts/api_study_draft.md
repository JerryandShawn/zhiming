# 研习区接口契约草稿 0.1.0

**草稿，未冻结、未实现。** 仅供主线采用；不注册路由、不修改现有服务。公共规则见 [公共契约](api_modules_common_draft.md)。所有错误响应使用公共 Error，HTTP 映射沿用公共错误表；每个端点允许的错误码列在 x-endpoints.errors。GET 的 request 表示规范化查询参数及路径外过滤条件，不是 GET body；路径 ID 使用公共 Id，subject_id 必须经服务端授权。

## 内容与个人进度分离

术语/课程是有版本和可追溯引用的只读知识材料，不形成用户事实，不携带出生资料、私有盘面或第三方聊天。列表查询 q 只是搜索，不触发模型生成；cursor绑定当前知识版本与查询条件。citations.locator 是本地知识定位符，不作为任意外网URL自动抓取。没有有效引用的材料不得冒充已核实课程。

Progress 单独属于认证owner，不能客户端指定owner或其他用户；lesson_id路径是唯一课程目标。不存在进度时返回 progress=null、revision=0，首次PUT用expected_revision=0；已有进度返回当前修订，修改时必须相等。ProgressView的外层revision必须与progress.revision一致（非null），这是服务端业务约束。lesson_version防止在已更新课程上盲记旧进度；版本不匹配409 REVISION_CONFLICT，保留bookmark草稿，重新核对内容。不自动将课程更新重置为完成或改写旧进度。

completed仅表示用户标记完成，不证明理解、评测通过或命理准确；本接口没有评分、付费、课程生成或研习skill运行能力。进度写与资料编辑无关联，不能把教材语句写入画像。稳定request_id同载荷返回原程序回执；超时同ID对账，不盲新增写；主线事务采用expected_revision，409保留草稿禁盲重提。禁止通过UpdateProgress注入content/citations/owner改变公共课程。

## 接线边界

这些是05/P10研习入口和已交付模块的候选接口，不假称现有HTTP/PG/前端已实现；知识版本发布、个人进度存储、登录与撤销链均由主线采用和验收，不新增迁移。没有数据时返回合法空列表，不能伪造课程或学习完成回执。

## 端点映射（全部 draft）

| 方法与路径 | 请求 Schema | 成功响应 Schema | expected_revision 所属资源 |
| --- | --- | --- | --- |
| GET /api/study/glossary | StudyQuery | GlossaryList | none |
| GET /api/study/lessons | StudyQuery | LessonList | none |
| GET /api/study/lessons/{lesson_id} | LessonQuery | Lesson | none |
| GET /api/study/progress/{lesson_id} | LessonQuery | ProgressView | none |
| PUT /api/study/progress/{lesson_id} | UpdateProgress | WriteResult | personal lesson progress (0 if absent) |

Schema 使用 JSON Schema2020-12；公共引用只由测试本地 Registry 解析，禁止运行时联网取 Schema。x-examples 为公开合成正例，测试同时生成缺字段、越界、未知字段等反例。Schema 不能代替事务授权、当前来源核验、修订比较或幂等执行。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:mingjing:api:study:draft:0.1.0",
  "$defs": {
    "StudyQuery": {
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
        "q": {
          "type": "string",
          "minLength": 1,
          "maxLength": 100
        }
      },
      "required": []
    },
    "Citation": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "source_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "version": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "locator": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200
        }
      },
      "required": [
        "source_id",
        "version",
        "locator"
      ]
    },
    "GlossaryEntry": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "term": {
          "type": "string",
          "minLength": 1,
          "maxLength": 100
        },
        "definition": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000
        },
        "version": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "citations": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/Citation"
          },
          "maxItems": 20,
          "minItems": 1
        }
      },
      "required": [
        "id",
        "term",
        "definition",
        "version",
        "citations"
      ]
    },
    "GlossaryList": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/GlossaryEntry"
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
    "Lesson": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "title": {
          "type": "string",
          "minLength": 1,
          "maxLength": 200
        },
        "version": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "content": {
          "type": "string",
          "minLength": 1,
          "maxLength": 20000
        },
        "citations": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/Citation"
          },
          "maxItems": 50,
          "minItems": 1
        }
      },
      "required": [
        "id",
        "title",
        "version",
        "content",
        "citations"
      ]
    },
    "LessonList": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "items": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/Lesson"
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
    "LessonQuery": {
      "type": "object",
      "additionalProperties": false,
      "properties": {},
      "required": []
    },
    "Progress": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "lesson_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "lesson_version": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "revision": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
        },
        "status": {
          "enum": [
            "not_started",
            "in_progress",
            "completed"
          ]
        },
        "bookmark": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 200
        }
      },
      "required": [
        "lesson_id",
        "lesson_version",
        "revision",
        "status",
        "bookmark"
      ]
    },
    "ProgressView": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "progress": {
          "anyOf": [
            {
              "$ref": "#/$defs/Progress"
            },
            {
              "type": "null"
            }
          ]
        },
        "revision": {
          "type": "integer",
          "minimum": 0,
          "maximum": 9007199254740991
        }
      },
      "required": [
        "progress",
        "revision"
      ],
      "allOf": [
        {
          "if": {
            "properties": {
              "progress": {
                "type": "null"
              }
            }
          },
          "then": {
            "properties": {
              "revision": {
                "const": 0
              }
            }
          },
          "else": {
            "properties": {
              "revision": {
                "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Revision"
              }
            }
          }
        }
      ]
    },
    "UpdateProgress": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "request_id": {
          "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/Id"
        },
        "expected_revision": {
          "type": "integer",
          "minimum": 0,
          "maximum": 9007199254740991
        },
        "lesson_version": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "status": {
          "enum": [
            "not_started",
            "in_progress",
            "completed"
          ]
        },
        "bookmark": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 200
        }
      },
      "required": [
        "request_id",
        "expected_revision",
        "lesson_version",
        "status",
        "bookmark"
      ]
    },
    "WriteResult": {
      "$ref": "urn:mingjing:api:common:draft:0.1.0#/$defs/WriteResult"
    }
  },
  "x-endpoints": [
    {
      "method": "GET",
      "path": "/api/study/glossary",
      "request": "StudyQuery",
      "response": "GlossaryList",
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
      "method": "GET",
      "path": "/api/study/lessons",
      "request": "StudyQuery",
      "response": "LessonList",
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
      "method": "GET",
      "path": "/api/study/lessons/{lesson_id}",
      "request": "LessonQuery",
      "response": "Lesson",
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
      "method": "GET",
      "path": "/api/study/progress/{lesson_id}",
      "request": "LessonQuery",
      "response": "ProgressView",
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
      "method": "PUT",
      "path": "/api/study/progress/{lesson_id}",
      "request": "UpdateProgress",
      "response": "WriteResult",
      "revision_resource": "personal lesson progress (0 if absent)",
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
      "schema": "StudyQuery",
      "value": {
        "limit": 10,
        "q": "合成"
      }
    },
    {
      "schema": "LessonQuery",
      "value": {}
    },
    {
      "schema": "GlossaryList",
      "value": {
        "items": [
          {
            "id": "synthetic:g1",
            "term": "合成术语",
            "definition": "合成释义",
            "version": "v1",
            "citations": [
              {
                "source_id": "synthetic:book1",
                "version": "v1",
                "locator": "chapter:1"
              }
            ]
          }
        ],
        "next_cursor": null
      }
    },
    {
      "schema": "LessonList",
      "value": {
        "items": [],
        "next_cursor": null
      }
    },
    {
      "schema": "Lesson",
      "value": {
        "id": "synthetic:l1",
        "title": "合成课程",
        "version": "v1",
        "content": "合成正文",
        "citations": [
          {
            "source_id": "synthetic:book1",
            "version": "v1",
            "locator": "chapter:1"
          }
        ]
      }
    },
    {
      "schema": "ProgressView",
      "value": {
        "progress": null,
        "revision": 0
      }
    },
    {
      "schema": "UpdateProgress",
      "value": {
        "request_id": "synthetic:r1",
        "expected_revision": 0,
        "lesson_version": "v1",
        "status": "in_progress",
        "bookmark": null
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
