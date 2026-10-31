import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { InteractiveAskCard } from '../src/chat/interactions/AskCard';
import { DecisionCards } from '../src/chat/interactions/DecisionCards';
import { MemoryCard } from '../src/chat/interactions/MemoryCard';
import { MemoryReceipts } from '../src/chat/interactions/MemoryReceipts';
import { rememberReceipt, type DisplayReceipt } from '../src/chat/interactions/memoryProjection';
import type { AskAnswerContext, AskAnswerReceipt, MemoryCommands } from '../src/chat/interactions/contracts';
import type { Decision, Question } from '../src/chat/types';

const question: Question = {
  askId: 'ask-synthetic-1',
  question: '这两件事，你想先看哪些？',
  options: ['安排', '准备'],
  optionIds: ['schedule', 'prepare'],
  multi: false,
  allow_free_text: true,
  why: '先按你的需要来',
};
function accepted(answer: string, context?: AskAnswerContext): AskAnswerReceipt {
  return { status: 'accepted', answer, request_id: 'synthetic-confirmed', ...context };
}
const commands: MemoryCommands = {
  supports: () => true,
  execute: vi.fn(async () => ({ write_status: 'saved' as const, fact_id: 'synthetic-fact' })),
};

describe('frozen v1 interactive questions', () => {
  it('binds confirmation to stable question and option IDs rather than display text', async () => {
    const submit = vi.fn(async (answer: string, context?: AskAnswerContext) => accepted(answer, context));
    render(<InteractiveAskCard question={question} onAnswer={submit} />);
    await userEvent.click(screen.getByRole('button', { name: '安排' }));
    expect(submit).toHaveBeenCalledWith('安排', { askId: 'ask-synthetic-1', optionIds: ['schedule'] });
    expect(screen.getByRole('button', { name: '安排' })).toHaveAttribute('data-option-id', 'schedule');
    expect(screen.getByText('你选了：安排')).toBeVisible();
    expect(screen.getAllByRole('button').every((button) => button.hasAttribute('disabled'))).toBe(true);
  });

  it('selects multiple items locally and sends one explicit confirmation in original option order', async () => {
    const submit = vi.fn(async (answer: string, context?: AskAnswerContext) => accepted(answer, context));
    render(<InteractiveAskCard question={{ ...question, multi: true }} onAnswer={submit} />);
    expect(screen.getByRole('button', { name: '确认选择' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '准备' }));
    await userEvent.click(screen.getByRole('button', { name: '安排' }));
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '准备' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: '确认选择' }));
    expect(submit).toHaveBeenCalledExactlyOnceWith('安排；准备', {
      askId: 'ask-synthetic-1',
      optionIds: ['schedule', 'prepare'],
    });
    expect(screen.getByText('你选了：安排；准备')).toBeVisible();
    expect(screen.getByRole('button', { name: '安排' })).toBeDisabled();
  });

  it('distinguishes two identically labeled options by ID when confirming and highlighting', async () => {
    const submit = vi.fn(async (answer: string, context?: AskAnswerContext) => accepted(answer, context));
    render(<InteractiveAskCard question={{ ...question, options: ['稍后', '稍后'] }} onAnswer={submit} />);
    const options = screen.getAllByRole('button', { name: '稍后' });
    await userEvent.click(options[1]);
    expect(submit).toHaveBeenCalledWith('稍后', { askId: question.askId, optionIds: ['prepare'] });
    expect(options[0]).toHaveAttribute('aria-pressed', 'false');
    expect(options[1]).toHaveAttribute('aria-pressed', 'true');
  });

  it.each(['missing-ids', 'wrong-question', 'wrong-option'] as const)(
    'does not mark a card answered after a %s acknowledgement',
    async (mismatch) => {
      const submit = vi.fn(async () => ({
        status: 'accepted' as const,
        answer: '安排',
        request_id: 'synthetic-mismatched',
        ...(mismatch === 'missing-ids'
          ? {}
          : {
              askId: mismatch === 'wrong-question' ? 'other-ask' : question.askId,
              optionIds: mismatch === 'wrong-option' ? ['other-option'] : ['schedule'],
            }),
      }));
      render(<InteractiveAskCard question={question} onAnswer={submit} />);
      await userEvent.click(screen.getByRole('button', { name: '安排' }));
      expect(screen.getByRole('alert')).toHaveTextContent('尚未收到回答确认');
      expect(screen.queryByText(/你选了/)).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: '安排' })).toBeEnabled();
    },
  );

  it('does not confirm a new question with the same words when an older acknowledgement arrives late', async () => {
    let resolve: (value: AskAnswerReceipt) => void = () => undefined;
    const submit = vi.fn(
      () =>
        new Promise<AskAnswerReceipt>((done) => {
          resolve = done;
        }),
    );
    const { rerender } = render(<InteractiveAskCard question={question} onAnswer={submit} />);
    await userEvent.click(screen.getByRole('button', { name: '安排' }));
    rerender(<InteractiveAskCard question={{ ...question, askId: 'next-ask' }} onAnswer={submit} />);
    await act(async () => resolve(accepted('安排', { askId: question.askId!, optionIds: ['schedule'] })));
    expect(screen.queryByText(/你选了/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '准备' })).toBeEnabled();
    expect(screen.getByRole('region', { name: '明镜的提问' })).toHaveAttribute('data-ask-id', 'next-ask');
  });

  it('does not invent IDs for malformed multi-select questions and still permits free text focus', async () => {
    const submit = vi.fn();
    render(
      <>
        <textarea id="composer-input" aria-label="主输入框" />
        <InteractiveAskCard question={{ ...question, multi: true, optionIds: [] }} onAnswer={submit} />
      </>,
    );
    expect(screen.getByRole('button', { name: '安排' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '确认选择' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '我自己说' }));
    expect(screen.getByRole('textbox')).toHaveFocus();
    expect(submit).not.toHaveBeenCalled();
  });
});

const decision: Decision = {
  id: 'option-synthetic-1',
  option: '先整理材料',
  benefit: '更容易说明经历',
  cost: '花一个晚上',
  risk: '未确定的信息不作结论',
  reversibility: 'easy',
  first_step: '先列三段经历',
  unknowns: [],
};
describe('frozen v1 decision display', () => {
  it('renders reversible enums as plain language and does not invent uncertainty for complete data', () => {
    render(
      <DecisionCards options={[decision, { ...decision, id: 'second', option: '直接演练', reversibility: 'hard' }]} />,
    );
    expect(screen.getByText('容易调整')).toBeVisible();
    expect(screen.getByText('较难撤回')).toBeVisible();
    expect(screen.queryByText('待确认')).not.toBeInTheDocument();
  });

  it('marks declared unknown dimensions pending instead of presenting a speculative value', () => {
    render(
      <DecisionCards
        options={[
          { ...decision, risk: '未经确认的风险描述', unknowns: ['risk', '当前能投入的时间'] },
          { ...decision, id: 'second', option: '先约时间', reversibility: 'unknown' },
        ]}
      />,
    );
    const first = screen.getByRole('heading', { name: '先整理材料' }).closest('section')!;
    expect(within(first).queryByText('未经确认的风险描述')).not.toBeInTheDocument();
    expect(within(first).getByLabelText('待确认事项')).toHaveTextContent('当前能投入的时间');
    expect(within(first).getAllByText('待确认')).toHaveLength(2);
    expect(first).toHaveAttribute('data-option-id', decision.id);
  });
});

describe('frozen v1 memory receipt states', () => {
  it('renders pending_confirm as an uncommitted proposal with explicit consent actions', () => {
    render(
      <MemoryCard
        commands={commands}
        receipt={{
          proposal_id: 'synthetic-proposal',
          write_status: 'pending_confirm',
          summary: '合成待确认信息',
          sensitive: true,
        }}
      />,
    );
    expect(screen.getByLabelText('待确认记忆')).toBeVisible();
    expect(screen.getByRole('button', { name: '记住' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '不用' })).toBeEnabled();
    expect(screen.getByText('待你确认，尚未保存为有效记忆')).toBeVisible();
  });

  it.each([
    ['undone', '已撤销，不会再提起'],
    ['rejected', '这条没有保存为记忆。'],
  ])('renders %s read-only with no write or undo actions', (write_status, text) => {
    render(
      <MemoryCard
        commands={commands}
        receipt={{
          fact_id: 'synthetic-fact',
          write_status,
          summary: '合成信息',
          sensitive: false,
        }}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent(text);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it.each(['undone', 'rejected'])(
    'keeps terminal %s over a stale saved replay, but accepts a later revision',
    (status) => {
      const seen = new Map<string, DisplayReceipt>();
      const terminal = { fact_id: 'synthetic-fact', write_status: status, revision: 3, summary: '合成信息' };
      rememberReceipt(seen, terminal);
      expect(rememberReceipt(seen, { ...terminal, write_status: 'saved' }).write_status).toBe(status);
      expect(rememberReceipt(seen, { ...terminal, write_status: 'saved', revision: 2 }).write_status).toBe(status);
      expect(rememberReceipt(seen, { ...terminal, write_status: 'saved', revision: 4 }).write_status).toBe('saved');
    },
  );

  it('does not expose an undo action when final repeats a saved receipt after a rejected event', () => {
    const { rerender } = render(
      <MemoryReceipts
        commands={commands}
        receipts={[{ fact_id: 'synthetic-fact', write_status: 'rejected', summary: '合成信息' }]}
      />,
    );
    rerender(
      <MemoryReceipts
        commands={commands}
        receipts={[{ fact_id: 'synthetic-fact', write_status: 'saved', summary: '合成信息' }]}
      />,
    );
    expect(screen.getByText('这条没有保存为记忆。')).toBeVisible();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
