import { useEffect, useState, useSyncExternalStore } from 'react';
import { createPrivacySession, type PrivacyOptions } from './session';

export function usePrivacySession(options: PrivacyOptions = {}) {
  const [controller] = useState(() => createPrivacySession(options));
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const { session } = snapshot;
  useEffect(() => {
    if (!session) return;
    const expire = () => controller.expire();
    const timeout = setTimeout(expire, Math.max(0, session.lastActivity + controller.idleMs - controller.now()));
    document.addEventListener('visibilitychange', expire);
    window.addEventListener('focus', expire);
    return () => {
      clearTimeout(timeout);
      document.removeEventListener('visibilitychange', expire);
      window.removeEventListener('focus', expire);
    };
  }, [controller, session]);
  useEffect(() => () => controller.exit(), [controller]);
  return {
    ...snapshot,
    active: Boolean(session),
    enter: controller.enter,
    exit: controller.exit,
    setActive: controller.setActive,
    setDraft: (text: string) => {
      if (session) controller.setDraft(session, text);
    },
    setImages: (images: string[]) => {
      if (session) controller.setImages(session, images);
    },
    send: () => (session ? controller.send(session) : Promise.resolve()),
    stop: () => {
      if (session) controller.stop(session);
    },
  };
}

export type PrivacySessionController = ReturnType<typeof usePrivacySession>;
