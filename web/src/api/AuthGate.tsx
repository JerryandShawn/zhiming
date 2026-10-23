import { useEffect, useState, type ComponentType, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { operationNamespace, useAuth } from './client';
import type { LoginDialogProps } from './LoginDialog';

export function AuthGate({ children }: { children: ReactNode }) {
  const required = useAuth((state) => state.loginRequired);
  const setToken = useAuth((state) => state.setToken);
  const cache = useQueryClient();
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [View, setView] = useState<ComponentType<LoginDialogProps> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  useEffect(() => {
    if (!required || View) return;
    let current = true;
    setLoadFailed(false);
    void import('./LoginDialog').then(
      (module) => {
        if (current) setView(() => module.default);
      },
      () => {
        if (current) setLoadFailed(true);
      },
    );
    return () => {
      current = false;
    };
  }, [required, View, loadAttempt]);
  async function login() {
    setBusy(true);
    setError('');
    try {
      const response = await fetch('/api/health', { headers: { 'X-Token': draft.trim() }, credentials: 'same-origin' });
      if (!response.ok) {
        setError('口令没有通过核对，请重新输入。你的草稿还在。');
        return;
      }
      const body: unknown = await response.json();
      if (!body || typeof body !== 'object' || !('ok' in body) || body.ok !== true) {
        setError('没有收到登录确认，请再试一次。');
        return;
      }
      if (useAuth.getState().token !== draft.trim()) cache.clear();
      setToken(draft.trim());
      setDraft('');
    } catch {
      setError('暂时没有连上，请稍后再试。你的草稿还在。');
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div key={operationNamespace()} className={required ? 'auth-hidden' : undefined}>
        {children}
      </div>
      {required &&
        (View ? (
          <View draft={draft} error={error} busy={busy} onDraftChange={setDraft} onSubmit={login} />
        ) : (
          <>
            <div className="overlay" />
            <div
              className="dialog login-dialog"
              role={loadFailed ? 'alert' : 'status'}
              aria-label={loadFailed ? '登录页面未展开' : '正在展开登录'}>
              <p>{loadFailed ? '登录页面暂时没有展开，请再试一次。' : '正在展开登录…'}</p>
              {loadFailed && (
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => {
                    setLoadFailed(false);
                    setLoadAttempt((value) => value + 1);
                  }}>
                  再试一次
                </button>
              )}
            </div>
          </>
        ))}
    </>
  );
}
