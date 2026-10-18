import { useEffect, useState } from 'react';

export function useKeyboardViewport() {
  const [keyboard, setKeyboard] = useState(false);
  const [height, setHeight] = useState<number>();
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    let baseline = window.innerHeight;
    const update = () => {
      const active = document.activeElement;
      const editing =
        active instanceof HTMLElement && active.matches('textarea, input:not([type="checkbox"]):not([type="file"])');
      if (!editing) baseline = window.innerHeight;
      const open = window.innerWidth < 1024 && editing && viewport.height < baseline - 120;
      setKeyboard(open);
      setHeight(open ? viewport.height : undefined);
    };
    viewport.addEventListener('resize', update);
    viewport.addEventListener('scroll', update);
    document.addEventListener('focusin', update);
    document.addEventListener('focusout', update);
    return () => {
      viewport.removeEventListener('resize', update);
      viewport.removeEventListener('scroll', update);
      document.removeEventListener('focusin', update);
      document.removeEventListener('focusout', update);
    };
  }, []);
  return { keyboard, height };
}
