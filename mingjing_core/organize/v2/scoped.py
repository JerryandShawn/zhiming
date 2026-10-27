"""Trusted message/context boundary; the text classifier itself never stores ambient history."""

from dataclasses import dataclass, field

from mingjing_core.organize.contracts import Message

from .classifier import LocalClassifier
from .contracts import ClassificationContext, Prediction


@dataclass(frozen=True)
class OrganizeScope:
    owner_id: str
    subject_id: str
    thread_id: str

    def __post_init__(self) -> None:
        if not all(type(value) is str and value.strip() for value in (self.owner_id, self.subject_id, self.thread_id)):
            raise ValueError("整理上下文需要有效归属")


@dataclass(frozen=True)
class ScopedContext:
    scope: OrganizeScope
    context: ClassificationContext = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.scope, OrganizeScope) or not isinstance(self.context, ClassificationContext):
            raise ValueError("整理上下文格式无效")


def require_message(message: Message, scope: OrganizeScope) -> None:
    if not isinstance(message, Message) or not isinstance(scope, OrganizeScope):
        raise ValueError("整理消息与归属无效")
    if (message.owner_id, message.subject_id, message.thread_id) != (
        scope.owner_id,
        scope.subject_id,
        scope.thread_id,
    ):
        raise ValueError("整理消息不能跨用户、人物或线程")
    if type(message.incognito) is not bool:
        raise ValueError("整理消息的无痕开关无效")
    if message.status != "active" or message.incognito or message.retention_scope != "persistent":
        raise ValueError("已撤回或无痕消息不能进入持久整理")
    if message.role != "user":
        raise ValueError("归区需要当前用户消息")


def classify_message(
    message: Message,
    *,
    scope: OrganizeScope,
    context: ScopedContext | None = None,
    classifier: LocalClassifier | None = None,
) -> Prediction:
    require_message(message, scope)
    if context is not None and (not isinstance(context, ScopedContext) or context.scope != scope):
        raise ValueError("整理上下文不能跨归属")
    engine = classifier or LocalClassifier()
    return engine.classify(message.content, context.context if context is not None else None)
