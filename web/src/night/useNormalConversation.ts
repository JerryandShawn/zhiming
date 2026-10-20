import { useEffect, useRef, useState } from 'react';
import { reduceChat } from '../chat/reducer';
import { initialStream } from '../chat/types';
import { playDemo, type DemoScenario } from './events';
import type { NightPort } from './port';
import { validAskAnswerReceipt, type AskAnswerContext } from '../chat/interactions/contracts';

// The ordinary conversation outlives its view. PrivateChat never receives this store.
export function useNormalConversation(port: NightPort, enabled: boolean) {
  const [state, setState] = useState(initialStream);
  const [scenario, setScenario] = useState<DemoScenario>('cards');
  const [round, setRound] = useState(0);
  const [draft, setDraft] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const [answered, setAnswered] = useState('');
  const [answeredOptionIds, setAnsweredOptionIds] = useState<string[]>();
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
    setAnswered('');
    setAnsweredOptionIds(undefined);
    setReply('');
    setBusy(true);
    void playDemo(
      scenario,
      (event) => {
        if (abort.signal.aborted) return;
        setState((current) => reduceChat(current, event));
        if (event.type === 'final' || event.type === 'error') {
          setBusy(false);
        }
      },
      abort.signal,
      100,
      { runId: `local-${mountId}-${episode}` },
    ).catch((reason: unknown) => {
      if (!abort.signal.aborted) setReply(reason instanceof Error ? reason.message : '演示暂时停下了。');
    });
    return () => abort.abort();
  }, [enabled, episode, scenario]);
  async function answer(text: string, context?: AskAnswerContext) {
    const question = latest.current.question;
    const source = question?.askId ? (context ?? { askId: question.askId, optionIds: [] }) : context;
    if (question?.askId) {
      if (source?.askId !== question.askId || new Set(source.optionIds).size !== source.optionIds.length)
        throw new Error('这张提问卡已变化，请重新选择。');
      const ids = question.optionIds ?? [];
      if (source.optionIds.some((id) => !ids.includes(id)) || (!question.multi && source.optionIds.length > 1))
        throw new Error('这次选择不属于当前提问。');
      const selected = ids.flatMap((id, index) => (source.optionIds.includes(id) ? [question.options[index]] : []));
      if (selected.length ? selected.join('；') !== text : !question.allow_free_text)
        throw new Error('请重新核对这次选择。');
    }
    const receipt = await port.answer(text, `local-answer-${mountId}-${episode}`, source);
    if (activeEpisode.current !== episode) throw new DOMException('这一轮已切换', 'AbortError');
    if (question?.askId && latest.current.question?.askId !== question.askId)
      throw new DOMException('提问已切换', 'AbortError');
    if (!validAskAnswerReceipt(receipt, text, source)) throw new Error('尚未收到当前提问的有效确认。');
    setAnswered(receipt.answer);
    setAnsweredOptionIds(receipt.optionIds);
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
    review: state.reviewPending ?? false,
    draft,
    setDraft,
    images,
    setImages,
    answered,
    answeredOptionIds,
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
