import { useEffect, useMemo, useRef, useState } from 'react';
import { followV1, type FollowV1ConnectionState, type FollowV1Result } from '../../chat/followV1';
import { initialStream } from '../../chat/types';
import { reduceChat } from '../../chat/reducer';
import { recoveryPortForLocation } from './port';
import type { RecoveryPort } from './types';

export function useRecovery(suppliedPort?: RecoveryPort) {
  const port = useMemo(() => suppliedPort ?? recoveryPortForLocation(new URL(location.href)), [suppliedPort]);
  const [version, setVersion] = useState(0);
  const [state, setState] = useState(initialStream);
  const [connection, setConnection] = useState<FollowV1ConnectionState>({ phase: 'connecting', attempt: 0 });
  const [result, setResult] = useState<FollowV1Result>();
  const [running, setRunning] = useState(false);
  const generation = useRef(0),
    active = useRef<AbortController>();
  useEffect(() => {
    const controller = new AbortController(),
      epoch = ++generation.current;
    active.current = controller;
    const current = () => !controller.signal.aborted && generation.current === epoch;
    setState(initialStream());
    setResult(undefined);
    setRunning(true);
    setConnection({ phase: 'connecting', attempt: 0 });
    void followV1(port.runId, {
      connect: port.connect,
      signal: controller.signal,
      retryMs: 500,
      maxReconnects: 3,
      accept: (event) => {
        if (current()) setState((prior) => (current() ? reduceChat(prior, event) : prior));
      },
      onConnectionState: (next) => {
        if (current()) setConnection(next);
      },
    })
      .then((next) => {
        if (!current()) return;
        setResult(next);
        setRunning(false);
      })
      .catch(() => {
        if (!current()) return;
        setResult({
          reason: 'failed',
          reconnects: 0,
          code: 'unavailable',
          error: '本地恢复暂未完成，已显示的内容保留。',
        });
        setConnection({ phase: 'failed', attempt: 0 });
        setRunning(false);
      });
    return () => {
      controller.abort();
    };
  }, [port, version]);
  function stop() {
    ++generation.current;
    active.current?.abort();
    setRunning(false);
    setConnection((prior) => ({ ...prior, phase: 'aborted' }));
  }
  function replay() {
    stop();
    setVersion((value) => value + 1);
  }
  return { state, connection, result, running, replay, stop, mode: port.mode, version };
}
