"""Stable provider-neutral tools; only application services execute business effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from mingjing_core.agent.tools.computation_definitions import computation_definitions
from mingjing_core.agent.tools.interaction_definitions import interaction_definitions
from mingjing_core.agent.tools.parameters import (
    CalendarLookup,
    MemoryForget,
    MemorySearch,
    MemoryWrite,
    NoteWrite,
    ProfileGet,
    TimeContext,
)
from mingjing_core.agent.tools.tarot_definitions import tarot_definitions
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult, tool_input_fingerprint
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolSpec
from mingjing_core.models.schema_flatten import flatten_schema

from .tool_visibility import select_visible

__all__ = ["ToolContext", "ToolResult", "ToolRegistry", "ToolDefinition"]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    parameters: type[BaseModel]
    description: str
    read_only: bool = True
    private_allowed: bool = False


DEFINITIONS = (
    (
        ToolDefinition(
            "time_context",
            TimeContext,
            "当回答今天、日期、节气或择日背景时使用。参数须为绝对日期；不推断用户行程、不做预测。返回当地时刻、农历干支、节气物理时刻、假日调休与宜忌；只读无副作用。",
        ),
        ToolDefinition(
            "calendar_lookup",
            CalendarLookup,
            "当比较连续日期或查看已确认事件时使用。只接受最多366日的绝对日期区间；未来假日安排未发布会明示，不把节日当放假。返回逐日历法、调休和授权事件；只读无副作用。",
        ),
        ToolDefinition(
            "memory_search",
            MemorySearch,
            "当需要查证用户既往事实、原话或笔记时使用；不用于全网搜索或证明象征解释。仅检索当前人物有效授权资料，撤销内容不可见。返回原话来源、实体类型和版本；只读无副作用。",
        ),
        ToolDefinition(
            "memory_write",
            MemoryWrite,
            "当当前用户明确陈述真实普通偏好、事件或目标时使用。必须逐字引用本轮用户消息；拒存秘密、假设和退出保存内容，"
            "敏感资料先提议确认，出生资料交资料更正工具，相对日期缺解析需确认。返回保存或待确认回执；会写事实或确认提议，支持幂等与撤销。",
            False,
        ),
        ToolDefinition(
            "memory_forget",
            MemoryForget,
            "仅当本轮用户明确要求忘记、删除或停止使用某事实时使用；目标不唯一需先询问，不能仅按模型猜测ID删除。返回删除或停用回执及受影响ID；会撤销原话区间并使派生资料失效，支持幂等。",
            False,
        ),
        ToolDefinition(
            "note_write",
            NoteWrite,
            "当需要保留基于本轮用户来源的推断笔记时使用；不适用已拒存、无痕或含凭据的内容，不能伪装用户事实。返回笔记ID和版本；会写明inferred并绑定来源，来源撤销后失效，支持幂等。",
            False,
        ),
        ToolDefinition(
            "profile_get",
            ProfileGet,
            "当回答依赖当前人物已确认资料时使用；不用于修改资料，也不自动采纳历史导入候选。返回已确认字段、来源事实与冲突字段；只读无副作用。",
        ),
    )
    + interaction_definitions()
    + tarot_definitions()
    + computation_definitions()
)


class ToolRegistry:
    def __init__(
        self,
        service: AgentToolsService,
        *,
        definitions: tuple[ToolDefinition, ...] = DEFINITIONS,
    ) -> None:
        if len({item.name for item in definitions}) != len(definitions):
            raise ValueError("工具名称必须唯一")
        self.service, self.definitions = service, definitions
        self._by_name = {item.name: item for item in definitions}

    def specs(self, ctx: ToolContext, *, required: tuple[str, ...] = ()) -> list[ToolSpec]:
        state = self.service.visibility_state(ctx)
        definitions = tuple(
            item for item in self.definitions if item.name != "chart_compute" or self.service.chart_available(ctx)
        )
        visible = select_visible(definitions, ctx, state, required=required)
        return [
            ToolSpec(item.name, item.description, flatten_schema(item.parameters.model_json_schema()))
            for item in visible
        ]

    def read_only(self, name: str) -> bool:
        return self._by_name[name].read_only

    def fingerprint(
        self, name: str, arguments: dict[str, Any], *, source_versions: dict[str, int] | None = None
    ) -> str:
        values = self._by_name[name].parameters.model_validate(arguments).model_dump()
        return tool_input_fingerprint(name, values, source_versions)

    def execute(self, name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            if name not in {spec.name for spec in self.specs(ctx, required=(name,))}:
                return ToolResult(
                    ok=False,
                    data={"code": "tool_unavailable"},
                    summary="当前模式下此工具不可用",
                )
            values = self._by_name[name].parameters.model_validate(arguments).model_dump()
            if tool_input_fingerprint(name, values, ctx.source_versions) != ctx.input_fp:
                return ToolResult(ok=False, data={"code": "tool_arguments_mismatch"}, summary="工具参数与持久步骤不符")
            return self.service.execute(name, values, ctx)
        except ValidationError:
            return ToolResult(
                ok=False,
                data={"code": "invalid_arguments"},
                summary="工具参数无效，请检查字段",
            )
        except CoreError as error:
            return ToolResult(
                ok=False,
                data={"code": error.code},
                summary="工具请求未通过身份或来源校验",
            )
        except (ValueError, KeyError):
            return ToolResult(
                ok=False,
                data={"code": "invalid_request"},
                summary="工具请求无效，未执行写入",
            )
