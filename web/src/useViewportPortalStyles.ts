import { useEffect } from 'react';
import type { KeyboardViewport } from './useKeyboardViewport';

// Portalled dialogs are outside .shell, so they share the same visual geometry at the document root.
export function useViewportPortalStyles({ keyboard, height, offsetTop }: KeyboardViewport) {
  useEffect(() => {
    const root = document.documentElement;
    const clear = () => {
      delete root.dataset.visualKeyboard;
      root.style.removeProperty('--app-vv-height');
      root.style.removeProperty('--app-vv-top');
    };
    if (!keyboard || height === undefined) {
      clear();
      return;
    }
    root.dataset.visualKeyboard = 'open';
    root.style.setProperty('--app-vv-height', `${height}px`);
    root.style.setProperty('--app-vv-top', `${offsetTop ?? 0}px`);
    return clear;
  }, [keyboard, height, offsetTop]);
}
