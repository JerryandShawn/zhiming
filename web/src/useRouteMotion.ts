import { useEffect, useRef, useSyncExternalStore } from 'react';

const preference = '(prefers-reduced-motion: reduce)';
function subscribe(update: () => void) {
  window.addEventListener('hashchange', update);
  return () => window.removeEventListener('hashchange', update);
}

/** Animate the new content after navigation; never retain or remount an old page. */
export function useRouteMotion() {
  const main = useRef<HTMLElement>(null);
  const hash = useSyncExternalStore(
    subscribe,
    () => location.hash,
    () => '',
  );
  const previous = useRef(hash);
  useEffect(() => {
    const changed = previous.current !== hash;
    previous.current = hash;
    const element = main.current;
    if (!changed || !element || typeof element.animate !== 'function') return;
    const media = window.matchMedia(preference);
    if (media.matches) return;
    const animation = element.animate([{ opacity: 0.72 }, { opacity: 1 }], {
      duration: 120,
      easing: 'ease-out',
    });
    const cancel = () => animation.cancel();
    media.addEventListener('change', cancel);
    return () => {
      media.removeEventListener('change', cancel);
      animation.cancel();
    };
  }, [hash]);
  return main;
}
