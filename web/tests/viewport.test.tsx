import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Layout, embeddedAppearance } from '../src/Layout';
import { useKeyboardViewport } from '../src/useKeyboardViewport';

class Viewport extends EventTarget {
  height = 844;
  offsetTop = 0;
  scale = 1;
}
let viewport: Viewport;
beforeEach(() => {
  viewport = new Viewport();
  vi.stubGlobal('visualViewport', viewport);
  vi.stubGlobal('innerWidth', 390);
  vi.stubGlobal('innerHeight', 844);
});
afterEach(() => vi.unstubAllGlobals());

describe('mobile visual viewport keyboard geometry', () => {
  it('reads height and visual offset only while a writable text control has a keyboard-sized reduction', async () => {
    render(<textarea aria-label="草稿" />);
    const { result } = renderHook(useKeyboardViewport);
    await userEvent.click(screen.getByRole('textbox'));
    act(() => {
      viewport.height = 420;
      viewport.offsetTop = 120;
      viewport.dispatchEvent(new Event('resize'));
    });
    expect(result.current).toEqual({ keyboard: true, height: 420, offsetTop: 120, scale: 1 });
    await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
    act(() => {
      viewport.offsetTop = 160;
      viewport.dispatchEvent(new Event('scroll'));
    });
    expect(result.current.offsetTop).toBe(160);
    await act(async () => {
      screen.getByRole('textbox').blur();
    });
    expect(result.current.keyboard).toBe(false);
    expect(result.current.height).toBeUndefined();
  });

  it.each([1.5, 2, NaN, 0])('does not mistake zoom or invalid scale %s for a keyboard', async (scale) => {
    render(<textarea aria-label="草稿" />);
    const { result } = renderHook(useKeyboardViewport);
    await userEvent.click(screen.getByRole('textbox'));
    act(() => {
      viewport.height = 300;
      viewport.scale = scale;
      viewport.dispatchEvent(new Event('resize'));
    });
    expect(result.current.keyboard).toBe(false);
    expect(result.current.height).toBeUndefined();
  });

  it.each(['checkbox', 'radio', 'range', 'file', 'date'])(
    'does not classify a %s control as a text keyboard',
    (type) => {
      render(<input type={type} aria-label="其他控件" />);
      const { result } = renderHook(useKeyboardViewport);
      act(() => {
        screen.getByLabelText('其他控件').focus();
        viewport.height = 300;
        viewport.dispatchEvent(new Event('resize'));
      });
      expect(result.current.keyboard).toBe(false);
    },
  );

  it('ignores read-only fields and small browser-toolbar height changes', async () => {
    const view = render(<textarea aria-label="草稿" readOnly />);
    const { result } = renderHook(useKeyboardViewport);
    await userEvent.click(screen.getByRole('textbox'));
    act(() => {
      viewport.height = 420;
      viewport.dispatchEvent(new Event('resize'));
    });
    expect(result.current.keyboard).toBe(false);
    view.rerender(<textarea aria-label="草稿" />);
    act(() => {
      viewport.height = 760;
      viewport.dispatchEvent(new Event('resize'));
    });
    expect(result.current.keyboard).toBe(false);
  });

  it('re-establishes the baseline on orientation/width changes and clears closed keyboards without blur', async () => {
    render(<textarea aria-label="草稿" />);
    const { result } = renderHook(useKeyboardViewport);
    await userEvent.click(screen.getByRole('textbox'));
    act(() => {
      viewport.height = 420;
      viewport.dispatchEvent(new Event('resize'));
    });
    expect(result.current.keyboard).toBe(true);
    act(() => {
      vi.stubGlobal('innerWidth', 844);
      vi.stubGlobal('innerHeight', 390);
      viewport.height = 390;
      window.dispatchEvent(new Event('orientationchange'));
    });
    expect(result.current.keyboard).toBe(false);
    act(() => {
      viewport.height = 200;
      viewport.dispatchEvent(new Event('resize'));
    });
    expect(result.current.keyboard).toBe(true);
    act(() => {
      viewport.height = 390;
      viewport.dispatchEvent(new Event('resize'));
    });
    expect(result.current.keyboard).toBe(false);
  });

  it('uses ordinary responsive layout when visualViewport is unavailable or the viewport is desktop', async () => {
    vi.stubGlobal('visualViewport', undefined);
    const first = renderHook(useKeyboardViewport);
    expect(first.result.current.keyboard).toBe(false);
    first.unmount();
    vi.stubGlobal('visualViewport', viewport);
    vi.stubGlobal('innerWidth', 1440);
    render(<textarea aria-label="草稿" />);
    const second = renderHook(useKeyboardViewport);
    await userEvent.click(screen.getByRole('textbox'));
    act(() => {
      viewport.height = 300;
      viewport.dispatchEvent(new Event('resize'));
    });
    expect(second.result.current.keyboard).toBe(false);
  });

  it('shares keyboard geometry with the chat shell and portalled dialog styles, then cleans it on unmount', async () => {
    const view = render(
      <Layout page="chat">
        <div className="page chat-page">
          <textarea aria-label="草稿" />
        </div>
      </Layout>,
    );
    await userEvent.type(screen.getByRole('textbox'), '未发送的合成草稿');
    act(() => {
      viewport.height = 420;
      viewport.offsetTop = 120;
      viewport.dispatchEvent(new Event('resize'));
    });
    const shell = document.querySelector('.shell')!;
    expect(shell).toHaveAttribute('data-keyboard', 'open');
    expect(shell).toHaveStyle({ '--keyboard-height': '420px', '--viewport-offset-top': '120px' });
    expect(document.documentElement).toHaveAttribute('data-visual-keyboard', 'open');
    expect(document.documentElement.style.getPropertyValue('--app-vv-height')).toBe('420px');
    expect(screen.getByRole('textbox')).toHaveValue('未发送的合成草稿');
    view.unmount();
    expect(document.documentElement).not.toHaveAttribute('data-visual-keyboard');
    expect(document.documentElement.style.getPropertyValue('--app-vv-height')).toBe('');
  });
});

describe('embedded appearance is independent of authentication', () => {
  it.each(['Mozilla/5.0 Mobile Lark/7.22', 'Mozilla/5.0 Feishu/8.0'])(
    'recognizes %s only as a presentation hint',
    (agent) => {
      expect(embeddedAppearance(agent)).toBe(true);
      vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(agent);
      render(
        <Layout page="me">
          <p>页面内容</p>
        </Layout>,
      );
      expect(document.querySelector('.shell')).toHaveAttribute('data-host', 'feishu');
      expect(screen.getByRole('main', { name: '关于我' })).toBeInTheDocument();
      expect(sessionStorage.getItem('mingjing-auth-token')).toBeNull();
    },
  );
  it('keeps normal browser presentation without a host marker', () => {
    expect(embeddedAppearance('Mozilla/5.0 Chrome/140')).toBe(false);
    render(
      <Layout page="chat">
        <p>页面内容</p>
      </Layout>,
    );
    expect(document.querySelector('.shell')).not.toHaveAttribute('data-host');
  });
});
