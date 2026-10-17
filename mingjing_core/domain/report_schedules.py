"""Report calendar policies; all dates use the fixed Asia/Shanghai timezone."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator
from mingjing_core.timekit.clock import get_clock

SHANGHAI = timezone(timedelta(hours=8))
KINDS = ('daily', 'weekly', 'monthly', 'quarterly')
LABELS = {'daily':'晨报', 'weekly':'周报', 'monthly':'月报', 'quarterly':'季报'}
TIME_PATTERN = r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]$'
POLICY_FIELDS = frozenset({'kind', 'enabled', 'time', 'weekday', 'day'})


class ReportSchedulePolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['daily', 'weekly', 'monthly', 'quarterly']
    enabled: StrictBool
    time: str = Field(pattern=TIME_PATTERN)
    weekday: StrictInt | None = Field(default=None, ge=1, le=7)
    day: StrictInt | Literal['last'] | None = None

    @model_validator(mode='after')
    def check_calendar(self):
        if self.kind == 'weekly':
            if self.weekday is None or self.day is not None:
                raise ValueError('周报仅配置 ISO 星期 1 至 7')
        elif self.weekday is not None:
            raise ValueError('仅周报可配置星期')
        if self.kind in ('monthly', 'quarterly'):
            if self.day != 'last' and (type(self.day) is not int or not 1 <= self.day <= 28):
                raise ValueError('月报与季报日期为 1 至 28 或 last')
        elif self.day is not None:
            raise ValueError('晨报与周报不能配置月日期')
        return self


class ReportSchedulePatch(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['daily', 'weekly', 'monthly', 'quarterly']
    request_id: str = Field(min_length=1, max_length=200)
    expected_revision: StrictInt = Field(ge=0)
    enabled: StrictBool | None = None
    time: str | None = Field(default=None, pattern=TIME_PATTERN)
    weekday: StrictInt | None = Field(default=None, ge=1, le=7)
    day: StrictInt | Literal['last'] | None = None

    @model_validator(mode='after')
    def check_changes(self):
        fields = self.model_fields_set - {'kind', 'request_id', 'expected_revision'}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError('需要至少一项明确的设置')
        if 'weekday' in fields and self.kind != 'weekly':
            raise ValueError('仅周报可配置星期')
        if 'day' in fields:
            if self.kind not in ('monthly', 'quarterly'):
                raise ValueError('仅月报与季报可配置月日期')
            if self.day != 'last' and (type(self.day) is not int or not 1 <= self.day <= 28):
                raise ValueError('日期为 1 至 28 或 last')
        return self


def default_policy(kind: str, *, enabled=True) -> dict:
    if kind not in KINDS:
        raise ValueError('报告类型无效')
    result = {'kind':kind, 'enabled':enabled,
              'time':{'daily':'07:00', 'weekly':'20:00', 'monthly':'09:00', 'quarterly':'10:00'}[kind]}
    if kind == 'weekly':result['weekday'] = 7
    if kind in ('monthly', 'quarterly'):result['day'] = 1
    return result


def schedule_on_day(kind: str, day: date, policy: dict | None = None):
    """Return this delivery occurrence; a policy never changes its frequency."""
    values = default_policy(kind) if policy is None else {key:value for key,value in policy.items() if key in POLICY_FIELDS}
    if values.get('kind') != kind:
        raise ValueError('报告类型与时间策略不一致')
    checked = ReportSchedulePolicy.model_validate(values)
    if not checked.enabled:
        return None
    if kind == 'weekly' and day.isoweekday() != checked.weekday:
        return None
    if kind in ('monthly', 'quarterly'):
        expected_day = calendar.monthrange(day.year,day.month)[1] if checked.day == 'last' else checked.day
        if day.day != expected_day:
            return None
    if kind == 'quarterly' and day.month not in (1,4,7,10):
        return None
    hour, minute = map(int,checked.time.split(':'))
    due = datetime(day.year,day.month,day.day,hour,minute,tzinfo=SHANGHAI)
    return {'prepare_at':due-timedelta(minutes=15), 'deliver_at':due, 'timezone':'Asia/Shanghai'}


def report_period(kind: str, day: date) -> str:
    if kind == 'daily':return day.isoformat()
    if kind == 'weekly':
        year, week, _ = day.isocalendar()
        return f'{year:04d}-W{week:02d}'
    if kind == 'monthly':return f'{day.year:04d}-{day.month:02d}'
    if kind == 'quarterly':return f'{day.year:04d}-Q{(day.month-1)//3+1}'
    raise ValueError('报告类型无效')


def report_period_bounds(kind: str, day: date) -> dict[str,str]:
    report_period(kind,day)
    start=end=day
    if kind=='weekly':
        start=day-timedelta(days=day.weekday());end=start+timedelta(days=6)
    elif kind in ('monthly','quarterly'):
        month=day.month if kind=='monthly' else (day.month-1)//3*3+1
        last_month=month if kind=='monthly' else month+2
        start=date(day.year,month,1)
        end=date(day.year,last_month,calendar.monthrange(day.year,last_month)[1])
    return {'start':start.isoformat(),'end':end.isoformat()}


def next_schedule(kind: str, policy: dict | None = None, *, now: datetime | None = None, blocked_periods=None):
    """Preview the next future delivery, including its preceding preparation."""
    current = now or get_clock().now()
    if current.tzinfo is None:
        raise ValueError('预览时刻需要时区')
    current = current.astimezone(SHANGHAI)
    # Preview still helps while paused; enabling is checked by the service.
    values = dict(default_policy(kind) if policy is None else policy, enabled=True)
    for offset in range(370):
        result = schedule_on_day(kind,current.date()+timedelta(days=offset),values)
        if result and result['deliver_at'] > current and report_period(kind,result['deliver_at'].date()) not in (blocked_periods or ()):
            return result
    raise ValueError('报告时间策略无法计算下次时刻')
