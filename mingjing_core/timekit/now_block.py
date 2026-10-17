"""Render authoritative current context without network or model inference."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .almanac import almanac, term_display
from .calendar_cn import day_status, holiday_window, next_holiday
from .clock import Clock


def instant(value: object, zone: ZoneInfo) -> datetime | None:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=zone)
        return parsed.astimezone(zone)
    except (ValueError, TypeError, OverflowError):
        return None


def status_text(day: date) -> str:
    status = day_status(day)
    labels = {
        "weekend": "周末，休息日（不是调休上班日）",
        "workday": "工作日",
        "holiday": f"{status.holiday_name}，法定放假日",
        "adjusted_workday": f"{status.holiday_name}调休上班日，需要上班",
    }
    result = labels[status.kind]
    if status.source == "unpublished":
        result += f"；{day.year} 年具体放假与调休安排尚未公布，仅按普通星期判断"
    window = holiday_window(day)
    if window:
        start, end = window
        result += (
            f"（{start.month}月{start.day}日–{end.month}月{end.day}日，"
            f"共 {(end - start).days + 1} 天，含今天还剩 {(end - day).days + 1} 天）"
        )
    return result


def recent_holiday(day: date) -> str:
    for offset in range(1, 61):
        past = day - timedelta(days=offset)
        window = holiday_window(past)
        if window:
            start, end = window
            status = day_status(past)
            adjustments = []
            for gap in range(1, 8):
                candidate = end + timedelta(days=gap)
                if day_status(candidate).kind == "adjusted_workday":
                    adjustments.append(
                        f"{candidate.month}月{candidate.day}日（周{'一二三四五六日'[candidate.weekday()]}）为调休上班日"
                    )
            suffix = "，" + "；".join(adjustments) if adjustments else ""
            return f"{status.holiday_name} {start.month}月{start.day}日–{end.month}月{end.day}日{suffix}"
    return "最近 60 天无已知法定放假安排"


def festival_text(now: datetime) -> str:
    for offset in range(8):
        candidate = now + timedelta(days=offset)
        values = almanac(candidate, now.tzinfo).festivals
        if values:
            label = "今天" if offset == 0 else "明天" if offset == 1 else f"{offset}天后"
            legal = day_status(candidate.date()).kind == "holiday"
            suffix = "法定假日安排" if legal else "传统或纪念节日，非法定放假安排"
            return (
                f"{label} {candidate.month}月{candidate.day}日（周{'一二三四五六日'[candidate.weekday()]}）"
                f"{'、'.join(values)}（{suffix}）"
            )
    return "未来 7 天无已知节日"


def interaction_text(value: object, now: datetime, zone: ZoneInfo) -> str:
    channel = value.get("channel", "未知渠道") if isinstance(value, dict) else "未知渠道"
    at = instant(value.get("at") if isinstance(value, dict) else value, zone)
    if at is None:
        return "无已知上次对话"
    days = (now.date() - at.date()).days
    distance = f"{days} 天" if days > 0 else "今天" if days == 0 else "记录时刻在当前时钟之后"
    return f"{distance}（上次：{at.month}月{at.day}日 {at:%H:%M}，{channel}）"


def event_text(events: list[dict], now: datetime, zone: ZoneInfo) -> str:
    selected = []
    for event in events:
        at = instant(event.get("event_at") or event.get("due") or event.get("due_at"), zone)
        if at is None or not now.date() <= at.date() <= now.date() + timedelta(days=7):
            continue
        text = str(event.get("title") or event.get("content") or "已确认安排")[:300]
        ref = f"〔{event['id']}〕" if event.get("id") else ""
        selected.append((at, f"{at.month}月{at.day}日（周{'一二三四五六日'[at.weekday()]}）{text}{ref}"))
    return "；".join(text for _, text in sorted(selected)) or "暂无已确认安排"


def render_now_block(owner_settings: dict, clock: Clock, last_interaction_at=None, upcoming_events=()) -> str:
    timezone = owner_settings.get("timezone", "Asia/Shanghai")
    zone = ZoneInfo(timezone)
    now = clock.now().astimezone(zone)
    value = almanac(now, zone)
    lunar, ganzhi, jieqi = value.lunar, value.ganzhi, value.jieqi
    holiday = next_holiday(now.date())
    future = (
        f"{holiday.name} {holiday.date.year}年{holiday.date.month}月{holiday.date.day}日"
        f"（周{'一二三四五六日'[holiday.date.weekday()]}），还有 {holiday.days_to} 天"
    )
    if not holiday.arrangement_published:
        future += f"；{holiday.date.year} 年具体放假与调休安排国务院尚未公布"
    zone_label = "北京时间" if timezone == "Asia/Shanghai" else timezone
    lines = [
        f'<此刻 tz="{timezone}" generated_at="{now.isoformat()}">',
        f"现在：{now.year}年{now.month}月{now.day}日 {value.weekday} {value.period} {now:%H:%M}（{zone_label}）",
        (
            f"农历：{lunar['year']}年（{lunar['zodiac']}年）"
            f"{'闰' if lunar['is_leap'] else ''}{lunar['month']}月{lunar['day']}"
        ),
        "干支："
        + " ".join(
            ganzhi[key] + unit for key, unit in (("year", "年"), ("month", "月"), ("day", "日"), ("hour", "时"))
        ),
        (
            f"节气：{jieqi['current']}（{term_display(jieqi['current_at'])} 交节）→ 下一个：{jieqi['next']}，"
            f"{term_display(jieqi['next_at'])}（还有 {jieqi['days_to_next']} 天）"
        ),
        f"今天：{status_text(now.date())}",
        f"最近的节日：{festival_text(now)}",
        f"下一个法定假日：{future}",
        f"刚过去的假期：{recent_holiday(now.date())}",
        (
            f"黄历：宜 {' '.join(value.yi)}；忌 {' '.join(value.ji)}；冲{value.chong}，煞{value.sha}；"
            f"建除 {value.zhixing}；星宿 {value.xiu}"
        ),
        f"距上次对话：{interaction_text(last_interaction_at, now, zone)}",
        f"未来 7 天你的安排：{event_text(list(upcoming_events), now, zone)}",
    ]
    if value.zi_hour_note:
        lines.append("晚子时口径：" + value.zi_hour_note)
    return "\n".join([*lines, "</此刻>"])
