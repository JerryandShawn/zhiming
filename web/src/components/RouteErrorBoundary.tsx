import { Component, useEffect, useId, useRef, type ReactNode } from 'react';
import { Button } from './ui/Controls';

type Props = {
  children: ReactNode;
  resetKey: string;
  homeHref?: string;
  atHome?: boolean;
  reloadNotice?: string;
  wrapFallback?: (recovery: ReactNode) => ReactNode;
  onReload?: () => void;
};
type State = { failed: boolean; resetKey: string };

function RouteRecovery({ homeHref = '#/today', atHome = false, reloadNotice, onReload }: Props) {
  const titleId = useId();
  const title = useRef<HTMLHeadingElement>(null);
  const reload = onReload ?? (() => location.reload());
  useEffect(() => {
    title.current?.focus({ preventScroll: true });
  }, []);
  return (
    <section className="page stack" role="alert" aria-labelledby={titleId} data-route-recovery>
      <h1 id={titleId} ref={title} tabIndex={-1}>
        这页暂时没有展开
      </h1>
      <p>可以先回到今日或使用导航查看其他页面，再重新载入当前页面。</p>
      {reloadNotice && <p className="meta">{reloadNotice}</p>}
      <div className="row wrap">
        <a
          className="button secondary"
          href={homeHref}
          onClick={(event) => {
            if (event.button || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
            const target = new URL(homeHref, location.href);
            const alreadyHome =
              target.origin === location.origin &&
              target.pathname === location.pathname &&
              target.search === location.search &&
              target.hash === '#/today' &&
              atHome;
            if (alreadyHome) {
              event.preventDefault();
              reload();
            }
          }}>
          回到今日
        </a>
        <Button onClick={reload}>重新载入页面</Button>
      </div>
    </section>
  );
}

/** Keep route failures below the navigation and controller owners. Never retain
 * an error object: import URLs, payloads and error messages are not UI content.
 * React.lazy caches a rejected import, so recovery uses a real document reload.
 */
export class RouteErrorBoundary extends Component<Props, State> {
  state: State = { failed: false, resetKey: this.props.resetKey };

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey === state.resetKey ? null : { failed: false, resetKey: props.resetKey };
  }

  static getDerivedStateFromError(): Partial<State> {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    const recovery = <RouteRecovery {...this.props} />;
    return this.props.wrapFallback ? this.props.wrapFallback(recovery) : recovery;
  }
}
