import { useState } from 'react';
import { ApiError } from '../api/client';
import { write } from '../api/operations';
import { Button } from '../components/ui/Controls';

export function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
export function text(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}
export function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record) : [];
}
export function message(error: unknown): string {
  return error instanceof Error ? error.message : '读取未完成，请稍后重试。';
}
export function localDate() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}
export function shownTime(value?: string | null) {
  if (!value) return '暂无安排';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? '时间待核对'
    : new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
      }).format(parsed);
}
export function ResourceState({ loading, error, retry }: { loading: boolean; error: unknown; retry: () => void }) {
  if (loading) return <p role="status">正在读取…</p>;
  if (error)
    return (
      <div className="error-banner" role="alert">
        <p>{message(error)}</p>
        <Button onClick={retry}>重新读取</Button>
      </div>
    );
  return null;
}
export function useCommand(scope: string) {
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [status, setStatus] = useState('');
  async function submit<T>(
    method: string,
    path: string,
    payload: Record<string, unknown>,
    receipt: (value: T) => boolean,
  ) {
    if (busy || conflict) return undefined;
    setBusy(true);
    setStatus('正在提交，等待服务器回执…');
    try {
      const result = await write<T>(scope, method, path, payload, { receipt });
      setStatus('已收到服务器确认。');
      return result;
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setConflict(true);
        setStatus('内容已在别处更新，草稿已保留。请读取最新版本并核对。');
      } else setStatus(`尚未确认提交：${message(error)}`);
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  return {
    busy,
    conflict,
    status,
    submit,
    setStatus,
    unlock: () => {
      setConflict(false);
      setStatus('已读取最新版本；草稿仍保留，请核对后再次保存。');
    },
  };
}
