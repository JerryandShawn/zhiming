import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import OnboardingChat from '../src/night/onboarding/OnboardingChat';
import { createOnboardingController } from '../src/night/onboarding/controller';
import { createBirthPort } from '../src/night/onboarding/birth';
import { createAboutMeStore } from '../src/night/me/port';
import type { BirthPort, OnboardingStep } from '../src/night/onboarding/types';

beforeEach(() => history.replaceState(null, '', '/?night=demo#/chat'));
function setup(step: OnboardingStep = 'welcome', birth: BirthPort = createBirthPort()) {
  const controller = createOnboardingController({ aboutMe: createAboutMeStore(), birth });
  controller.start();
  if (step !== 'welcome') {
    controller.continue();
    while (controller.getSnapshot().step !== step) controller.skip();
  }
  return { controller, birth };
}

it('shows a single current subquestion and keeps a paused draft for explicit continuation', async () => {
  const { controller, birth } = setup('user_name');
  render(<OnboardingChat controller={controller} birth={birth} />);
  expect(screen.getByRole('region', { name: '相识这轮问题' })).toHaveTextContent('你希望我怎么称呼你？');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await userEvent.type(screen.getByRole('textbox', { name: '相识这轮回答' }), '暂停时保留的称呼');
  await userEvent.click(screen.getByRole('button', { name: '先到这里' }));
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '继续相识' }));
  expect(screen.getByRole('textbox', { name: '相识这轮回答' })).toHaveValue('暂停时保留的称呼');
});

it('reads private birth fields only in its Sheet, starts empty and cancellation does not confirm', async () => {
  const base = createBirthPort(),
    readPrivate = vi.fn(base.readPrivate),
    confirm = vi.fn(base.confirm);
  const { controller, birth } = setup('birth', { ...base, readPrivate, confirm });
  render(<OnboardingChat controller={controller} birth={birth} />);
  expect(readPrivate).not.toHaveBeenCalled();
  const trigger = screen.getByRole('button', { name: '补充出生资料' });
  await userEvent.click(trigger);
  expect(readPrivate).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('textbox', { name: '阳历出生日期' })).toHaveValue('');
  expect(screen.getByLabelText('当地出生时间')).toHaveValue('');
  expect(screen.getByRole('textbox', { name: '出生地名称' })).toHaveValue('');
  expect(screen.getByRole('button', { name: '确认并保存资料' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: '取消' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(confirm).not.toHaveBeenCalled();
  expect(controller.getSnapshot().step).toBe('birth');
  await waitFor(() => expect(trigger).toHaveFocus());
});

it('accepts date-only consent and removes raw values from the subsequent conversation', async () => {
  const { controller, birth } = setup('birth');
  render(<OnboardingChat controller={controller} birth={birth} />);
  await userEvent.click(screen.getByRole('button', { name: '补充出生资料' }));
  await userEvent.type(screen.getByRole('textbox', { name: '阳历出生日期' }), '1998-03-12');
  expect(screen.getByRole('button', { name: '确认并保存资料' })).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox', { name: '我已核对并授权保存出生资料' }));
  await userEvent.click(screen.getByRole('button', { name: '确认并保存资料' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(controller.getSnapshot().step).toBe('current_life');
  expect(birth.readSummary()).toMatchObject({ status: 'partial', confirmedFields: ['date'] });
  expect(birth.readPrivate().draft.time).toBe('');
  expect(document.body).not.toHaveTextContent('1998-03-12');
  expect(JSON.stringify(controller.getSnapshot())).not.toContain('1998-03-12');
});

it('keeps the exact three outreach choices and asks changed report time in a later turn', async () => {
  const { controller, birth } = setup('outreach');
  render(<OnboardingChat controller={controller} birth={birth} />);
  for (const name of ['可以', '晨报换个时间', '先别主动找我'])
    expect(screen.getByRole('button', { name })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '晨报换个时间' }));
  await waitFor(() => expect(controller.getSnapshot().step).toBe('outreach_time'));
  expect(screen.getByRole('textbox', { name: '相识这轮回答' })).toHaveValue('');
  expect(screen.getByRole('region', { name: '相识这轮问题' })).toHaveTextContent('HH:mm');
});

it('shows a safe closing and an explicit unavailable gift instead of a manufactured chart', () => {
  const { controller, birth } = setup('summary');
  render(<OnboardingChat controller={controller} birth={birth} />);
  expect(screen.getByRole('region', { name: '相识小结' })).toHaveTextContent('见面礼还在等可核对的排盘结果。');
  expect(screen.getByRole('button', { name: '完成相识' })).toBeInTheDocument();
  expect(screen.queryByText(/你是甲木|你是丁火/)).not.toBeInTheDocument();
});

it('pauses the guided controller before handing the view back to the ordinary conversation', async () => {
  const { controller, birth } = setup('user_name');
  const leave = vi.fn(() => expect(controller.getSnapshot().status).toBe('paused'));
  render(<OnboardingChat controller={controller} birth={birth} onLeave={leave} />);
  await act(async () => controller.setDraft('引导的独立草稿'));
  await userEvent.click(screen.getByRole('button', { name: '先聊别的' }));
  expect(leave).toHaveBeenCalledTimes(1);
  expect(controller.getSnapshot().draft).toBe('引导的独立草稿');
});

it('locks an uncertain original answer while allowing only its exact retry', async () => {
  const base = createAboutMeStore(),
    birth = createBirthPort();
  const execute = vi.fn().mockRejectedValue(new Error('network'));
  const controller = createOnboardingController({ aboutMe: { ...base, execute }, birth });
  controller.start();
  controller.continue();
  while (controller.getSnapshot().step !== 'outreach') controller.skip();
  render(<OnboardingChat controller={controller} birth={birth} />);
  await userEvent.click(screen.getByRole('button', { name: '可以' }));
  await waitFor(() => expect(controller.getSnapshot().hasPending).toBe(true));
  expect(screen.getByRole('textbox', { name: '相识这轮回答' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '晨报换个时间' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '先别主动找我' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '可以' })).toBeEnabled();
  expect(screen.getByRole('button', { name: '重试原回答' })).toBeEnabled();
  await userEvent.click(screen.getByRole('button', { name: '重试原回答' }));
  expect(execute.mock.calls[1][0]).toBe(execute.mock.calls[0][0]);
});

it('scrolls to the current step after transitions and keeps typing from resetting the scroll position', async () => {
  vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((callback) => {
    callback(0);
    return 1;
  });
  const scroll = vi.spyOn(Element.prototype, 'scrollIntoView');
  const { controller, birth } = setup('user_name');
  render(<OnboardingChat controller={controller} birth={birth} />);
  const initial = scroll.mock.calls.length;
  expect(scroll).toHaveBeenLastCalledWith({ block: 'end', behavior: 'auto' });
  await act(async () => controller.setDraft('写草稿时不跳回底部'));
  expect(scroll).toHaveBeenCalledTimes(initial);
  await act(async () => controller.pause());
  expect(scroll).toHaveBeenCalledTimes(initial + 1);
  await act(async () => controller.resume());
  expect(scroll).toHaveBeenCalledTimes(initial + 2);
});
