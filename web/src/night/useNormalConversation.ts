import { useEffect, useRef, useState } from 'react';
import { reduceChat } from '../chat/reducer';
import { initialStream } from '../chat/types';
import { playDemo, type DemoScenario } from './events';
import type { NightPort } from './port';

// The ordinary conversation outlives its view. PrivateChat never receives this store.
export function useNormalConversation(port: NightPort, enabled: boolean) {
  const [state, setState] = useState(initialStream);
  const [scenario, setScenario] = useState<DemoScenario>('cards');
  const [round, setRound] = useState(0);
  const [review, setReview] = useState(false);
  const [draft, setDraft] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const [answered, setAnswered] = useState('');
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController>();
  const mountId = useRef(crypto.randomUUID()).current;
  const latest = useRef(state);
  latest.current = state;
  const episode = `${scenario}-${round}`;
  const activeEpisode = useRef(episode);
  activeEpisode.current = episode;
  const played = useRef('');
  useEffect(() => {
    if (!enabled || (played.current === episode && (latest.current.complete || latest.current.error))) return;
    const abort = new AbortController();
    played.current = episode;
    controller.current = abort;
    setState(initialStream());
    setReview(false);
    setAnswered('');
    setReply('');
    setBusy(true);
    void playDemo(
      scenario,
      (event, pending) => {
        if (abort.signal.aborted) return;
        setState((current) => reduceChat(current, event));
        if (pending !== undefined) setReview(pending);
        if (event.type === 'final' || event.type === 'error') {
          setBusy(false);
          setReview(false);
        }
      },
      abort.signal,
    ).catch((reason: unknown) => {
      if (!abort.signal.aborted) setReply(reason instanceof Error ? reason.message : '演示暂时停下了。');
    });
    return () => abort.abort();
  }, [enabled, episode, scenario]);
  async function answer(text: string) {
    const receipt = await port.answer(text, `local-answer-${mountId}-${episode}`);
    if (activeEpisode.current !== episode) throw new DOMException('这一轮已切换', 'AbortError');
    setAnswered(receipt.answer);
    setDraft('');
    setReply('已收到你的选择。接下来会开启新一轮对话（本地演示）。');
    return receipt;
  }
  function replay(next: DemoScenario) {
    setScenario(next);
    setRound((value) => value + 1);
  }
  function pause() {
    controller.current?.abort();
    setBusy(false);
    setReview(false);
  }
  function stop() {
    pause();
    setState((current) => ({ ...current, complete: true, status: '' }));
    setReply('已停止本地演示，尚未完成的步骤没有确认。');
  }
  function send() {
    if (state.question && !answered)
      void answer(draft).catch((reason: unknown) =>
        setReply(reason instanceof Error ? reason.message : '尚未收到确认。'),
      );
    else {
      setReply('这里只演示卡片的选择，你写的内容仍留在输入框。');
    }
  }
  return {
    state,
    scenario,
    round,
    review,
    draft,
    setDraft,
    images,
    setImages,
    answered,
    reply,
    busy,
    answer,
    replay,
    pause,
    stop,
    send,
  };
}
export type NormalConversation = ReturnType<typeof useNormalConversation>;
