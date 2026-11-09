import type { OnboardingKnown, OnboardingPrompt, OnboardingStep } from './types';

export const stepOrder: OnboardingStep[] = [
  'welcome',
  'user_name',
  'assistant_name',
  'birth',
  'current_life',
  'priorities',
  'directness',
  'terminology',
  'answer_length',
  'outreach',
  'summary',
  'done',
];
export const KNOWN_ONBOARDING_FIXTURE: OnboardingKnown = {
  user_name: true,
  assistant_name: true,
  directness: true,
  terminology: true,
  answer_length: true,
};
export const stageFor = (step: OnboardingStep) =>
  step === 'welcome'
    ? 1
    : ['user_name', 'assistant_name'].includes(step)
      ? 2
      : step === 'birth'
        ? 3
        : ['current_life', 'priorities'].includes(step)
          ? 4
          : ['directness', 'terminology', 'answer_length'].includes(step)
            ? 5
            : ['outreach', 'outreach_time'].includes(step)
              ? 6
              : 7;
const prompts: Record<OnboardingStep, OnboardingPrompt> = {
  welcome: {
    text: '我是明镜，会记得你明确告诉我的事；每次保存都有回执，可随时撤销。私人内容先问你。这是本地初次相识演示。',
    why: '我们可以慢慢认识，随时暂停。',
    options: ['开始认识'],
  },
  user_name: { text: '你希望我怎么称呼你？', why: '按你喜欢的方式称呼。', options: [] },
  assistant_name: { text: '你想怎么叫我？默认可以叫明镜。', why: '也可以给我起个顺口的名字。', options: ['明镜'] },
  birth: {
    text: '愿意提供一些排盘资料吗？只给日期、时刻不确定都可以。',
    why: '原值只在专门确认卡里核对，不进入聊天或普通画像。',
    options: ['核对出生资料', '暂时跳过'],
  },
  current_life: { text: '最近过得怎么样？', why: '先认识你当下的生活。', options: [] },
  priorities: { text: '最近最在意的一两件事是什么？', why: '从你最关心的地方开始。', options: [] },
  directness: { text: '沟通时喜欢直说，还是委婉一点？', why: '找到你舒服的表达方式。', options: ['直说', '委婉一点'] },
  terminology: {
    text: '命理术语多一点，还是少一点？',
    why: '按你的熟悉程度交流。',
    options: ['术语多一点', '术语少一点'],
  },
  answer_length: { text: '回答喜欢长一点，还是短一点？', why: '信息量由你决定。', options: ['长一点', '短一点'] },
  outreach: {
    text: '本地演示的联系偏好：晨报07:00、约好的事再问、22:00到08:00不打扰，这样可以吗？',
    why: '这里只确认本地偏好，不会启用真实飞书投递。',
    options: ['可以', '晨报换个时间', '先别主动找我'],
  },
  outreach_time: { text: '晨报想改到几点？请写HH:mm。', why: '仅保存本地联系偏好。', options: [] },
  summary: {
    text: '谢谢你让我多认识了一点。已确认的内容会在关于我中展示，也可修改或删除。出生资料只留在专门确认处。见面礼仍待真实排盘计算，本地演示不会编造日主或性格结论。',
    why: '你随时可以补充资料或继续自己的问题。',
    options: ['完成相识'],
  },
  done: { text: '这次初次相识已完成，可以回到普通对话。', why: '', options: [] },
};
export const promptFor = (step: OnboardingStep): OnboardingPrompt => ({
  ...prompts[step],
  options: [...prompts[step].options],
});
