"""Privacy-only card preview projection, without followup scheduling imports."""

SENSITIVE_PREVIEW = "明镜想问问你"
SENSITIVE_CATEGORIES = frozenset(
    {
        "health",
        "wellbeing",
        "medical",
        "money",
        "finance",
        "financial",
        "健康",
        "身心",
        "金钱",
        "财务",
    }
)


def safe_preview(
    text: str, category: str = "", *, proactive: bool = True, sensitive: bool = False
) -> str:
    if not isinstance(text, str) or not isinstance(category, str):
        raise ValueError("预览与类别必须是文本")
    if type(proactive) is not bool or type(sensitive) is not bool:
        raise ValueError("预览开关无效")
    return (
        SENSITIVE_PREVIEW
        if proactive
        and (sensitive or category.strip().casefold() in SENSITIVE_CATEGORIES)
        else text
    )
