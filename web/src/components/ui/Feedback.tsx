import { useEffect, type ReactNode } from 'react';
import { AlertCircle } from 'lucide-react';
import { Button, Seal } from './Controls';
import { useUi } from '../../state';

export function Toast() {
  const toast = useUi((state) => state.toast);
  const notify = useUi((state) => state.notify);
  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => notify(''), 4000);
    return () => window.clearTimeout(timeout);
  }, [toast, notify]);
  return toast ? (
    <div className="toast" role="status">
      {toast}
    </div>
  ) : null;
}

export function EmptyState({ text, action, href }: { text: string; action: string; href: string }) {
  return (
    <div className="empty-state">
      <Seal size="large" />
      <p>{text}</p>
      <a href={href} className="button primary">
        {action}
      </a>
    </div>
  );
}

export function ErrorBanner({
  title = '这次没有连上',
  children,
  action,
}: {
  title?: string;
  children: ReactNode;
  action?: () => void;
}) {
  return (
    <div className="error-banner" role="alert">
      <h3 className="row">
        <AlertCircle className="icon" />
        {title}
      </h3>
      <p>{children}</p>
      {action && <Button onClick={action}>再试一次</Button>}
    </div>
  );
}

export function Skeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="stack small">
      <div className="skeleton" />
      <div className="skeleton" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
