import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { CalendarDays } from 'lucide-react';
import { TodayCalendar } from '../../calendar/TodayCalendar';
import { unavailableCalendar, validDate } from '../../calendar/data';
import { Button, Input, Seal, Tag } from '../../components/ui/Controls';
import { BEIJING_TIME_ZONE, beijingDateKey, systemClock } from '../../time/beijing';
import type { SettingsPort } from '../settings/types';
import { morningReportNote, todaySchedule } from './schedule';
import type { TodayPort } from './types';
import TodayTransitState, { type TodayLoad } from './TodayTransitState';
import './today.css';

type Props = { port: TodayPort; settings: SettingsPort; now?: () => Date; onChat?: () => void };
type Load = TodayLoad;

const headingFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: BEIJING_TIME_ZONE,
  month: 'long',
  day: 'numeric',
  weekday: 'long',
});
const timeFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: BEIJING_TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});
const placements: Record<string, string> = {
  ready: '到期可查看',
  scheduled: '还没到时间',
  'quiet-hold': '免打扰后再提醒',
  'inbox-only': '仅留在收件箱',
  paused: '跟进已关闭',
};

export default function TodayPage({ port, settings, now = systemClock.now, onChat }: Props) {
  const preferences = useSyncExternalStore(settings.subscribe, settings.getSnapshot);
  const [instant, setInstant] = useState(now);
  const clockValid = Number.isFinite(instant.getTime());
  const today = clockValid ? beijingDateKey(instant) : '';
  const previousToday = useRef(today);
  const [selectedDate, setSelectedDate] = useState(today);
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<Load>({ status: 'loading', date: today });
  const plans = todaySchedule(instant, preferences);
  useEffect(() => {
    const tick = () => setInstant(now());
    const timer = setInterval(tick, 60 * 1000);
    window.addEventListener('focus', tick);
    document.addEventListener('visibilitychange', tick);
    return () => {
      clearInterval(timer);
      window.removeEventListener('focus', tick);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [now]);
  useEffect(() => {
    if (previousToday.current !== today) {
      const previous = previousToday.current;
      setSelectedDate((selected) => (selected === previous ? today : selected));
      previousToday.current = today;
    }
  }, [today]);
  useEffect(() => {
    const abort = new AbortController();
    setLoaded({ status: 'loading', date: selectedDate });
    if (!validDate(selectedDate)) {
      setLoaded({ status: 'invalid', date: selectedDate });
      return () => abort.abort();
    }
    void port
      .read(selectedDate, abort.signal)
      .then((result) => {
        if (abort.signal.aborted) return;
        setLoaded(
          result.date === selectedDate && (result.status !== 'ready' || result.transit.date === selectedDate)
            ? result
            : { status: 'error', date: selectedDate },
        );
      })
      .catch(() => {
        if (!abort.signal.aborted) setLoaded({ status: 'error', date: selectedDate });
      });
    return () => abort.abort();
  }, [port, selectedDate, attempt]);
  const view: Load = !validDate(selectedDate)
    ? { status: 'invalid', date: selectedDate }
    : loaded.date === selectedDate
      ? loaded
      : { status: 'loading', date: selectedDate };
  return (
    <div
      className="page night-today"
      data-page="today"
      data-runtime="night-today"
      data-today={today}
      data-view-date={selectedDate}
      data-load-state={view.status}>
      <div className="page-grid">
        <div className="today-main">
          <header className="stack small">
            <h1 className="today-date">{clockValid ? headingFormat.format(instant) : '本地时间暂不可用'}</h1>
            <p className="meta">晨报视图 · 北京时间{today ? ` · ${today}` : ''}</p>
            <p className="meta">节假日、调休、农历及节气资料尚未载入，暂不作判断。</p>
          </header>
          <div className="greeting">
            <Seal size="large" />
            <div>
              <p className="greeting-voice">先看看今天要做的事，再留一点空间给自己。</p>
              <p className="meta">明镜 · 本地合成预览</p>
            </div>
          </div>
          <section className="section" aria-labelledby="today-plans-title">
            <h2 id="today-plans-title">今天的安排与提醒</h2>
            <p className="meta">以下均为合成安排，只预览，不会推送。</p>
            <ul className="today-plans" aria-label="安排与提醒列表">
              {plans.map((item) => (
                <li key={item.id} data-plan-id={item.id} data-placement={item.placement}>
                  <div className="today-plan-heading">
                    <h3>{item.title}</h3>
                    <Tag>{placements[item.placement] ?? '待核对'}</Tag>
                  </div>
                  <p className="meta">
                    {item.dueAt.slice(0, 10) === today ? '今天' : item.dueAt.slice(0, 10)}{' '}
                    {timeFormat.format(new Date(item.dueAt))} ·{' '}
                    {item.kind === 'followup' ? '主动跟进' : '你明确设定的提醒'}
                  </p>
                  <p className="small-text secondary-text">{item.note}</p>
                </li>
              ))}
            </ul>
            {!plans.length && <p className="meta">今天暂没有可展示的到期安排。</p>}
          </section>
          <section className="section" aria-labelledby="today-transit-title">
            <h2 id="today-transit-title">{selectedDate === today ? '今日流日' : '浏览流日'}</h2>
            <label className="field today-date-field">
              查看哪天的流日
              <Input
                type="date"
                aria-label="查看哪天的流日"
                aria-invalid={!validDate(selectedDate) || undefined}
                aria-describedby={!validDate(selectedDate) ? 'today-date-hint' : undefined}
                value={selectedDate}
                onChange={(event) => setSelectedDate(event.target.value)}
              />
            </label>
            {selectedDate !== today && (
              <p className="meta">
                正在浏览 {selectedDate || '未选日期'}；今天的日期与安排保持不变。
                <Button variant="ghost" disabled={!today} onClick={() => setSelectedDate(today)}>
                  看今天的流日
                </Button>
              </p>
            )}
            <TodayTransitState view={view} port={port} retry={() => setAttempt((value) => value + 1)} />
          </section>
        </div>
        <aside className="page-aside today-aside night-today-aside" aria-label="日历与订阅">
          <section className="today-clock">
            <p className="meta">此刻 · 北京时间</p>
            <h2>{clockValid ? timeFormat.format(instant) : '时间待核对'}</h2>
            <p className="small-text">浏览月历或流日，不会改动今天的安排。</p>
          </section>
          {today && <TodayCalendar today={today} source={unavailableCalendar} />}
          <section className="section stack small" aria-labelledby="today-report-title">
            <h2 id="today-report-title">晨报与联系</h2>
            <p className="small-text">{morningReportNote(today, preferences)}</p>
            <p className="meta">
              免打扰 {preferences.contact.dndStart}–{preferences.contact.dndEnd}；主动跟进
              {preferences.contact.followup ? `每天最多 ${preferences.contact.dailyCap} 条` : '已关闭'}。
            </p>
            <a className="text-link quiet-link" href="#/settings">
              调整报告与联系设置
            </a>
          </section>
          <section className="section stack small">
            <h2 className="row">
              <CalendarDays className="icon" aria-hidden="true" />
              今天先做一小步
            </h2>
            <p className="small-text secondary-text">命理要点只作文化与学习参考。实际安排、身心感受和你的选择优先。</p>
          </section>
        </aside>
      </div>
      <div className="today-action">
        <a
          className="button primary block"
          href="#/chat"
          onClick={(event) => {
            if (onChat) {
              event.preventDefault();
              onChat();
            }
          }}>
          和明镜聊聊
        </a>
      </div>
    </div>
  );
}
