export type SpreadKind = 'focus1' | 'reflect3' | 'choice5';
export type TarotDraft = {
  spread: SpreadKind;
  method: string;
  reverse: boolean;
  question: string;
  optionA: string;
  optionB: string;
};
export const spreadCounts = { focus1: 1, reflect3: 3, choice5: 5 } as const;
export const spreadNames = { focus1: '看一件事', reflect3: '梳理问题', choice5: 'A/B选择' } as const;
