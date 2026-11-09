import { useEffect, useRef } from 'react';
import { operationNamespace } from '../../api/client';

export function useInteractionGuard() {
  const namespace = useRef(operationNamespace()).current;
  const mounted = useRef(true),
    active = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const current = () => mounted.current && namespace === operationNamespace();
  return {
    current,
    begin: () => {
      if (!current() || active.current) return false;
      active.current = true;
      return true;
    },
    end: () => {
      active.current = false;
    },
  };
}
