import { useEffect, useState } from 'react';

export type KeyboardViewport = { keyboard: boolean; height?: number; offsetTop?: number; scale: number };
const closed: KeyboardViewport = { keyboard: false, scale: 1 };
function textControl(element: Element | null): element is HTMLInputElement | HTMLTextAreaElement {
  return (
    (element instanceof HTMLTextAreaElement ||
      (element instanceof HTMLInputElement &&
        ['text', 'search', 'email', 'password', 'tel', 'url', 'number'].includes(element.type))) &&
    !element.disabled &&
    !element.readOnly
  );
}
export function useKeyboardViewport() {
  const [state, setState] = useState<KeyboardViewport>(closed);
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    let baseline = Math.max(window.innerHeight, Number.isFinite(viewport.height) ? viewport.height : 0);
    let width = window.innerWidth;
    let alive = true;
    const update = () => {
      if (!alive) return;
      const editing = textControl(document.activeElement);
      const validScale = Number.isFinite(viewport.scale) && viewport.scale > 0;
      const scale = validScale ? viewport.scale : 1;
      const height = Number.isFinite(viewport.height) ? Math.max(0, viewport.height) : 0;
      const offsetTop = Number.isFinite(viewport.offsetTop) ? Math.max(0, viewport.offsetTop) : 0;
      const unscaled = validScale && Math.abs(scale - 1) < 0.02;
      // A width/orientation change must not retain the old portrait baseline.
      if (unscaled && (!editing || width !== window.innerWidth)) baseline = Math.max(window.innerHeight, height);
      width = window.innerWidth;
      const keyboard = window.innerWidth < 1024 && editing && unscaled && height > 0 && height < baseline - 120;
      const next: KeyboardViewport = keyboard ? { keyboard, height, offsetTop, scale } : { keyboard: false, scale };
      setState((previous) =>
        previous.keyboard === next.keyboard &&
        previous.height === next.height &&
        previous.offsetTop === next.offsetTop &&
        previous.scale === next.scale
          ? previous
          : next,
      );
    };
    const afterBlur = () => queueMicrotask(update);
    viewport.addEventListener('resize', update);
    viewport.addEventListener('scroll', update);
    window.addEventListener('resize', update);
    window.addEventListener('orientationchange', update);
    document.addEventListener('focusin', update);
    document.addEventListener('focusout', afterBlur);
    update();
    return () => {
      alive = false;
      viewport.removeEventListener('resize', update);
      viewport.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
      window.removeEventListener('orientationchange', update);
      document.removeEventListener('focusin', update);
      document.removeEventListener('focusout', afterBlur);
    };
  }, []);
  useEffect(() => {
    if (!state.keyboard) return;
    const frame = requestAnimationFrame(() => {
      const active = document.activeElement;
      if (textControl(active)) active.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    });
    return () => cancelAnimationFrame(frame);
  }, [state.keyboard, state.height, state.offsetTop]);
  return state;
}
