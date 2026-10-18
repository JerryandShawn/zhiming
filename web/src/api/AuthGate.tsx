import { useState, type ReactNode } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useQueryClient } from '@tanstack/react-query';
import { Button, Input, Seal } from '../components/ui/Controls';
import { operationNamespace, useAuth } from './client';

export function AuthGate({ children }: { children: ReactNode }) {
  const required = useAuth((state) => state.loginRequired);
  const setToken = useAuth((state) => state.setToken);
  const cache = useQueryClient();
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
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
      <Dialog.Root open={required}>
        <Dialog.Portal>
          <Dialog.Overlay className="overlay" />
          <Dialog.Content
            className="dialog login-dialog"
            onEscapeKeyDown={(event) => event.preventDefault()}
            onPointerDownOutside={(event) => event.preventDefault()}>
            <Seal size="large" />
            <Dialog.Title asChild>
              <h2>登录明镜台</h2>
            </Dialog.Title>
            <Dialog.Description className="meta">输入网站口令。本页仅在当前浏览会话中保存登录。</Dialog.Description>
            <form
              className="stack"
              onSubmit={(event) => {
                event.preventDefault();
                void login();
              }}>
              <label className="field">
                网站口令
                <Input
                  type="password"
                  autoComplete="current-password"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  required
                />
              </label>
              {error && (
                <p role="alert" className="field-error">
                  {error}
                </p>
              )}
              <Button variant="primary" type="submit" loading={busy}>
                登录
              </Button>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
