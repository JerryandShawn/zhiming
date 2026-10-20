import * as Dialog from '@radix-ui/react-dialog';
import { Button, Input, Seal } from '../components/ui/Controls';

export type LoginDialogProps = {
  draft: string;
  error: string;
  busy: boolean;
  onDraftChange: (value: string) => void;
  onSubmit: () => Promise<void>;
};

export default function LoginDialog({ draft, error, busy, onDraftChange, onSubmit }: LoginDialogProps) {
  return (
    <Dialog.Root open>
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
              void onSubmit();
            }}>
            <label className="field">
              网站口令
              <Input
                type="password"
                autoComplete="current-password"
                value={draft}
                onChange={(event) => onDraftChange(event.target.value)}
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
  );
}
