import { AboutMeError, type AboutMeCommand, type AboutMeReceipt, type ProfileSection } from '../me/types';
import { safeText } from '../me/model';
import { KNOWN_ONBOARDING_FIXTURE, promptFor, stageFor, stepOrder } from './steps';
import type { OnboardingContactPreference } from '../settings/types';
import type {
  BirthReceipt,
  OnboardingController,
  OnboardingKnown,
  OnboardingOptions,
  OnboardingSnapshot,
  OnboardingStep,
} from './types';

const sections: Partial<Record<OnboardingStep, ProfileSection>> = {
  user_name: 'basic',
  assistant_name: 'basic',
  current_life: 'current_life',
  priorities: 'goals',
  directness: 'communication',
  terminology: 'communication',
  answer_length: 'communication',
  outreach: 'communication',
  outreach_time: 'communication',
};
const labels: Partial<Record<OnboardingStep, string>> = {
  user_name: '希望称呼为',
  assistant_name: '称呼明镜为',
  current_life: '最近的生活',
  priorities: '在意的事',
  directness: '表达方式',
  terminology: '术语偏好',
  answer_length: '回答长度',
  outreach: '本地联系偏好',
  outreach_time: '本地晨报时间',
};

export function createOnboardingController(options: OnboardingOptions): OnboardingController {
  const uuid = options.uuid ?? (() => crypto.randomUUID());
  let known: OnboardingKnown = {},
    pending: { command: AboutMeCommand; text: string; step: OnboardingStep } | undefined;
  const safeAnswers = new Map<OnboardingStep, string>();
  let snapshot: OnboardingSnapshot = {
    sessionId: uuid(),
    generation: 0,
    stage: 1,
    step: 'welcome',
    status: 'idle',
    busy: false,
    hasPending: false,
    draft: '',
    prompt: promptFor('welcome'),
    messages: [],
    conflicted: false,
  };
  const listeners = new Set<() => void>();
  const publish = (patch: Partial<OnboardingSnapshot>) => {
    snapshot = { ...snapshot, ...patch, hasPending: Boolean(pending) };
    for (const listener of [...listeners]) listener();
  };
  const isKnown = (step: OnboardingStep) =>
    step === 'birth'
      ? options.birth.readSummary().status !== 'unconfirmed'
      : step !== 'welcome' && step !== 'summary' && step !== 'done' && step !== 'outreach_time' && known[step] === true;
  function nextStep(after: OnboardingStep): OnboardingStep {
    let next = after === 'outreach_time' ? 'summary' : (stepOrder[stepOrder.indexOf(after) + 1] ?? 'done');
    while (isKnown(next)) next = stepOrder[stepOrder.indexOf(next) + 1] ?? 'done';
    return next;
  }
  function go(step: OnboardingStep, userText?: string, refresh = false) {
    const prompt = promptFor(step);
    if (step === 'summary') {
      const name = safeAnswers.get('user_name'),
        life = safeAnswers.get('current_life'),
        priorities = safeAnswers.get('priorities');
      const communication = ['directness', 'terminology', 'answer_length']
        .map((key) => safeAnswers.get(key as OnboardingStep))
        .filter(Boolean);
      const contact = options.readContactPreference?.();
      prompt.text = [
        name ? `我会按你确认的称呼“${name}”来叫你。` : '称呼仍以你已经明确确认的资料为准，缺少的可以以后再补。',
        life || priorities
          ? `你刚才提到${[life, priorities].filter(Boolean).join('；')}。`
          : '你可以按自己的节奏告诉我近况，不需要一次说完。',
        communication.length
          ? `沟通时我会记得你偏好${communication.join('、')}。`
          : '沟通偏好沿用你明确确认的内容，未知项不会替你决定。',
        contact
          ? `当前本地联系设置：晨报${contact.dailyEnabled ? contact.time : '已关闭'}，跟进${contact.followup ? '开启' : '关闭'}，免打扰${contact.dndStart}至${contact.dndEnd}；真实投递尚未启用。`
          : safeAnswers.has('outreach')
            ? `本地联系偏好已确认为“${safeAnswers.get('outreach')}”${safeAnswers.has('outreach_time') ? `，晨报时间${safeAnswers.get('outreach_time')}` : ''}，真实投递尚未启用。`
            : '你随时可以修改或删除已确认的内容。',
        '见面礼仍待真实排盘计算，本地演示不会编造日主或性格结论。',
      ].join('');
    }
    const messages = [...snapshot.messages];
    if (userText) messages.push({ id: uuid(), role: 'user', text: userText });
    if (refresh) {
      let last = -1;
      for (let index = messages.length - 1; index >= 0; index--) {
        if (messages[index].role === 'assistant' && messages[index].text === snapshot.prompt.text) {
          last = index;
          break;
        }
      }
      if (last >= 0) messages[last] = { ...messages[last], text: prompt.text };
    } else messages.push({ id: uuid(), role: 'assistant', text: prompt.text });
    publish({
      step,
      stage: stageFor(step),
      status: step === 'done' ? 'complete' : 'active',
      busy: false,
      draft: '',
      error: undefined,
      conflicted: false,
      prompt,
      messages,
    });
  }
  function validAck(result: AboutMeReceipt, operation: NonNullable<typeof pending>) {
    const item = options.aboutMe.getSnapshot().profileItems.find((row) => row.id === operation.command.id);
    return (
      result?.requestId === operation.command.requestId &&
      result.kind === 'profile-edit' &&
      result.id === operation.command.id &&
      result.write_status === 'saved' &&
      Number.isInteger(result.revision) &&
      result.revision === operation.command.expectedRevision + 1 &&
      item?.revision === result.revision &&
      item.status === 'active' &&
      item.userEdited &&
      operation.command.type === 'profile-edit' &&
      item.text === operation.command.text &&
      Boolean(
        result.factId &&
        result.sourceId &&
        item.factIds.includes(result.factId) &&
        item.sourceIds.includes(result.sourceId),
      )
    );
  }
  async function submit(value = snapshot.draft) {
    if (snapshot.status !== 'active' || snapshot.busy || snapshot.conflicted) return;
    if (/^(?:先到这里?|改天继续|暂停)[。！!]?$/u.test(value.trim())) {
      pause();
      return;
    }
    const step = snapshot.step;
    if (!sections[step]) return;
    let text: string;
    try {
      text = safeText(value);
      if (step === 'outreach' && !promptFor(step).options.includes(text))
        throw new AboutMeError('INVALID', 422, '请选择一种本地联系偏好。');
      if (step === 'outreach_time' && !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(text))
        throw new AboutMeError('INVALID', 422, '请填写有效HH:mm时间。');
      if (pending && (pending.step !== step || pending.text !== text))
        throw new AboutMeError('INVALID', 422, '原提交尚未确认，请用原内容重试。');
      if (!pending) {
        const id = `onboarding-${step}`,
          current = options.aboutMe.getSnapshot().profileItems.find((item) => item.id === id);
        pending = {
          step,
          text,
          command: Object.freeze({
            type: 'profile-edit',
            id,
            section: sections[step]!,
            text: `${labels[step]}：${text}`,
            expectedRevision: current?.revision ?? 0,
            requestId: `onboarding:${snapshot.sessionId}:${step}:${uuid()}`,
          }),
        };
      }
    } catch (reason) {
      publish({ error: reason instanceof Error ? reason.message : '请核对内容。' });
      return;
    }
    const operation = pending,
      generation = snapshot.generation,
      sessionId = snapshot.sessionId;
    publish({ busy: true, error: undefined, draft: text });
    try {
      const result = await options.aboutMe.execute(operation.command);
      if (generation !== snapshot.generation || sessionId !== snapshot.sessionId || snapshot.status !== 'active')
        return;
      if (!validAck(result, operation)) throw new AboutMeError('INVALID', 502, '尚未收到匹配的确认，请用原内容重试。');
      const preference: OnboardingContactPreference | undefined =
        step === 'outreach_time'
          ? { requestId: operation.command.requestId, choice: 'custom-time', time: text }
          : step === 'outreach' && text !== '晨报换个时间'
            ? { requestId: operation.command.requestId, choice: text === '可以' ? 'allow' : 'off' }
            : undefined;
      if (preference && options.onContactPreference) {
        const contact = await options.onContactPreference(preference);
        if (generation !== snapshot.generation || sessionId !== snapshot.sessionId || snapshot.status !== 'active')
          return;
        const projection = contact?.projection,
          enabled = preference.choice !== 'off';
        if (
          contact?.kind !== 'contact-preference' ||
          contact.write_status !== 'saved' ||
          contact.requestId !== preference.requestId ||
          !Number.isInteger(contact.revision) ||
          contact.revision !== projection?.revision ||
          !projection.local ||
          projection.followup !== enabled ||
          projection.dailyEnabled !== enabled ||
          (enabled && projection.time !== (preference.time ?? '07:00'))
        )
          throw new AboutMeError('INVALID', 502, '联系设置尚未收到匹配确认，请用原回答重试。');
      }
      safeAnswers.set(step, text);
      if (step !== 'outreach_time') known[step as keyof OnboardingKnown] = true;
      pending = undefined;
      go(step === 'outreach' && text === '晨报换个时间' ? 'outreach_time' : nextStep(step), text);
    } catch (reason) {
      if (generation !== snapshot.generation || sessionId !== snapshot.sessionId) return;
      publish({
        busy: false,
        conflicted: Boolean(reason && typeof reason === 'object' && 'status' in reason && reason.status === 409),
        error: reason instanceof Error ? reason.message : '尚未确认，请用原内容重试。',
      });
    } finally {
      if (generation === snapshot.generation && sessionId === snapshot.sessionId && snapshot.busy)
        publish({ busy: false });
    }
  }
  function pause() {
    if (snapshot.status === 'active') publish({ status: 'paused', generation: snapshot.generation + 1, busy: false });
  }
  return {
    getSnapshot: () => snapshot,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    start(mode) {
      if (!mode && snapshot.status !== 'idle') return;
      safeAnswers.clear();
      known = mode === 'new' ? {} : { ...(options.known ?? (mode === 'known' ? KNOWN_ONBOARDING_FIXTURE : {})) };
      pending = undefined;
      publish({
        sessionId: uuid(),
        generation: snapshot.generation + 1,
        stage: 1,
        step: 'welcome',
        status: 'active',
        busy: false,
        draft: '',
        error: undefined,
        conflicted: false,
        prompt: promptFor('welcome'),
        messages: [{ id: uuid(), role: 'assistant', text: promptFor('welcome').text }],
      });
    },
    pause,
    resume() {
      if (snapshot.status === 'paused') {
        if (snapshot.step === 'summary') go('summary', undefined, true);
        else publish({ status: 'active' });
      }
    },
    continue() {
      if (snapshot.status === 'paused') {
        if (snapshot.step === 'summary') go('summary', undefined, true);
        else publish({ status: 'active' });
        return;
      }
      if (snapshot.status === 'active' && !snapshot.busy && ['welcome', 'summary'].includes(snapshot.step))
        go(nextStep(snapshot.step));
    },
    setDraft(value) {
      if (!snapshot.busy && !pending) publish({ draft: value });
    },
    submit,
    skip() {
      if (
        snapshot.status === 'active' &&
        !snapshot.busy &&
        !pending &&
        !['welcome', 'summary', 'done'].includes(snapshot.step)
      )
        go(nextStep(snapshot.step));
    },
    reconcile() {
      if (!snapshot.conflicted || snapshot.busy) return;
      options.aboutMe.getSnapshot();
      pending = undefined;
      publish({ conflicted: false, error: '已读取最新版本，草稿保留；请核对后再次提交。' });
    },
    birthConfirmed(receipt: BirthReceipt) {
      if (snapshot.status !== 'active' || snapshot.step !== 'birth') return false;
      const summary = options.birth.readSummary();
      if (
        receipt?.kind !== 'birth-confirm' ||
        receipt.write_status !== 'saved' ||
        !receipt.requestId ||
        receipt.revision !== summary.revision ||
        receipt.confirmation !== summary.status ||
        JSON.stringify([...receipt.confirmedFields].sort()) !== JSON.stringify([...summary.confirmedFields].sort())
      )
        return false;
      go(nextStep('birth'));
      return true;
    },
  };
}
