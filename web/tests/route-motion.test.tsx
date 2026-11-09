import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useRouteMotion } from '../src/useRouteMotion';

class MotionPreference extends EventTarget {
  matches = false;
}
let media: MotionPreference;
const cancellations: ReturnType<typeof vi.fn>[] = [];
const animate = vi.fn(() => {
  const cancel = vi.fn();
  cancellations.push(cancel);
  return { cancel };
});
const original = Object.getOwnPropertyDescriptor(Element.prototype, 'animate');
beforeEach(() => {
  history.replaceState({}, '', '/#/today');
  media = new MotionPreference();
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => media),
  );
  cancellations.length = 0;
  animate.mockClear();
  Object.defineProperty(Element.prototype, 'animate', { configurable: true, value: animate });
});
afterEach(() => {
  vi.unstubAllGlobals();
  if (original) Object.defineProperty(Element.prototype, 'animate', original);
  else Reflect.deleteProperty(Element.prototype, 'animate');
});
function Example({ text = '当前页面' }: { text?: string }) {
  const main = useRouteMotion();
  return (
    <main ref={main}>
      <p>{text}</p>
      <input aria-label="未发送的草稿" defaultValue="保留这段合成文字" />
    </main>
  );
}
function route(hash: string) {
  act(() => {
    history.pushState({}, '', hash);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

describe('route entry motion', () => {
  it('does not animate the initial page or ordinary updates and keeps the same live input node', () => {
    const view = render(<Example />);
    const input = screen.getByRole('textbox');
    view.rerender(<Example text="同一页的新回执" />);
    expect(animate).not.toHaveBeenCalled();
    route('#/chat');
    expect(screen.getByRole('textbox')).toBe(input);
    expect(input).toHaveValue('保留这段合成文字');
    expect(animate).toHaveBeenCalledWith([{ opacity: 0.72 }, { opacity: 1 }], { duration: 120, easing: 'ease-out' });
  });

  it('ignores same-URL panel history and cancels the old animation before the next route', () => {
    render(<Example />);
    route('#/me');
    act(() => {
      history.pushState({ __mingjing_panel: 'synthetic-panel' }, '', location.href);
      window.dispatchEvent(new PopStateEvent('popstate'));
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(animate).toHaveBeenCalledTimes(1);
    expect(cancellations[0]).not.toHaveBeenCalled();
    route('#/settings');
    expect(cancellations[0]).toHaveBeenCalledOnce();
    expect(animate).toHaveBeenCalledTimes(2);
  });

  it('honors reduced motion at navigation and cancels an in-flight effect as soon as the preference changes', () => {
    media.matches = true;
    render(<Example />);
    route('#/chat');
    expect(animate).not.toHaveBeenCalled();
    act(() => {
      media.matches = false;
      media.dispatchEvent(new Event('change'));
    });
    expect(animate).not.toHaveBeenCalled();
    route('#/chart');
    expect(animate).toHaveBeenCalledOnce();
    act(() => {
      media.matches = true;
      media.dispatchEvent(new Event('change'));
    });
    expect(cancellations[0]).toHaveBeenCalledOnce();
  });

  it('cancels on unmount and remains usable in containers without the Web Animations API', () => {
    const view = render(<Example />);
    route('#/chart');
    view.unmount();
    expect(cancellations[0]).toHaveBeenCalledOnce();
    Reflect.deleteProperty(Element.prototype, 'animate');
    render(<Example />);
    route('#/me');
    expect(screen.getByRole('textbox')).toHaveValue('保留这段合成文字');
    expect(animate).toHaveBeenCalledOnce();
  });
});
