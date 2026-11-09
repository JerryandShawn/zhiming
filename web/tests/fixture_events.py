"""Synthetic SSE v2 envelopes for the local frontend protocol fixture only."""

V2_STARTED = {
    "thread_id": "synthetic-thread",
    "message_id": "synthetic-message",
}

V2_EVENTS = [
    ("status", {"text": "正在核对合成资料"}),
    ("tool_call", {"name": "time_context", "summary": "核对日期"}),
    ("text_delta", {"text": "待复核的旧说法。"}),
    ("tool_result", {"name": "time_context", "summary": "日期已核对"}),
    ("text_reset", {"text": "复核后的合成回答。", "reason": "revised"}),
    (
        "memory_receipt",
        {
            "fact_id": "synthetic-fact",
            "write_status": "saved",
            "summary": "合成偏好",
        },
    ),
    (
        "ask_user",
        {
            "question": "想先看哪一项？",
            "options": ["安排", "准备"],
            "allow_free_text": True,
            "why": "只询问一个明确问题",
        },
    ),
    (
        "present_options",
        {
            "options": [
                {
                    "title": "先准备",
                    "benefit": "更从容",
                    "cost": "需要时间",
                    "risk": "待确认",
                    "reversibility": "可调整",
                    "first_step": "列清单",
                },
                {
                    "title": "先休息",
                    "benefit": "恢复精神",
                    "cost": "占用准备时间",
                    "risk": "待确认",
                    "reversibility": "可调整",
                    "first_step": "安排睡眠",
                },
            ],
        },
    ),
    (
        "final",
        {
            "message_id": "synthetic-message",
            "envelope": {"answer": "复核后的合成回答。"},
        },
    ),
]
