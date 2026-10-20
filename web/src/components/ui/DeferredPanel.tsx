import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
  type RefObject,
} from 'react';
import { usePanelHistory } from '../../usePanelHistory';
import { Button } from './Controls';

export type DialogContentProps = {
  title: string;
  description: string;
  children: ReactNode;
  sheet: boolean;
  contentId: string;
  onOpenChange: (open: boolean) => void;
  onReturnFocus: () => void;
};
type ContentModule = { default: ComponentType<DialogContentProps> };
type TriggerProps = {
  ref: RefObject<HTMLButtonElement>;
  onClick: () => void;
  'aria-haspopup': 'dialog';
  'aria-expanded': boolean;
  'aria-controls': string | undefined;
};
const loadDialogContent = () => import('./DialogContent');

// Keep the trigger and browser-history owner mounted while the dialog code loads.
export function DeferredPanel({
  title,
  description,
  children,
  sheet = false,
  renderTrigger,
  loadContent = loadDialogContent,
}: {
  title: string;
  description: string;
  children: ReactNode;
  sheet?: boolean;
  renderTrigger: (props: TriggerProps) => ReactNode;
  loadContent?: () => Promise<ContentModule>;
}) {
  const { open, onOpenChange } = usePanelHistory();
  const trigger = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  const latestOpen = useRef(false);
  const contentId = useId();
  const [Content, setContent] = useState<ComponentType<DialogContentProps> | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const returnFocus = useCallback(() => {
    if (latestOpen.current) return;
    const target = trigger.current?.isConnected ? trigger.current : document.getElementById('main');
    target?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    latestOpen.current = open;
    if (wasOpen.current && !open) returnFocus();
    wasOpen.current = open;
  }, [open, returnFocus]);

  useEffect(() => {
    if (!open || Content) return;
    let current = true;
    void Promise.resolve()
      .then(loadContent)
      .then(
        (module) => {
          if (current) setContent(() => module.default);
        },
        () => {
          if (current) setFailed(true);
        },
      );
    return () => {
      current = false;
    };
  }, [open, Content, loadContent, attempt]);

  useEffect(() => {
    if (!open || Content) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented) {
        event.preventDefault();
        onOpenChange(false);
      }
    };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [open, Content, onOpenChange]);

  const show = () => {
    setFailed(false);
    onOpenChange(true);
  };
  return (
    <>
      {renderTrigger({
        ref: trigger,
        onClick: show,
        'aria-haspopup': 'dialog',
        'aria-expanded': open,
        'aria-controls': open ? contentId : undefined,
      })}
      {open &&
        (Content ? (
          <Content
            title={title}
            description={description}
            sheet={sheet}
            contentId={contentId}
            onOpenChange={onOpenChange}
            onReturnFocus={returnFocus}>
            {children}
          </Content>
        ) : (
          <div
            id={contentId}
            role={failed ? 'alert' : 'status'}
            aria-label={`${failed ? '无法' : '正在'}展开${title}`}
            className="stack small">
            <p className="meta">{failed ? '这次没有展开，请再试一次。' : `正在展开${title}…`}</p>
            {failed && (
              <Button
                onClick={() => {
                  setFailed(false);
                  setAttempt((value) => value + 1);
                }}>
                再试一次
              </Button>
            )}
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              取消展开
            </Button>
          </div>
        ))}
    </>
  );
}
