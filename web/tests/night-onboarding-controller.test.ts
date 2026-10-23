import { describe, expect, it, vi } from 'vitest';
import { createAboutMeStore } from '../src/night/me/port';
import { createOnboardingController } from '../src/night/onboarding/controller';
import { createBirthPort, emptyBirthDraft } from '../src/night/onboarding/birth';
import type { AboutMeCommand } from '../src/night/me/types';
import type { OnboardingStep } from '../src/night/onboarding/types';

function setup() {
  const aboutMe = createAboutMeStore(),
    birth = createBirthPort();
  return { aboutMe, birth, controller: createOnboardingController({ aboutMe, birth }) };
}
describe('typed local onboarding controller', () => {
  it('visits seven stages in subturns, confirms safe data and summarizes only acknowledged answers', async () => {
    const { controller, aboutMe } = setup();
    controller.start('new');
    expect(controller.getSnapshot().stage).toBe(1);
    controller.continue();
    const answers: [OnboardingStep, string][] = [
      ['user_name', '小远'],
      ['assistant_name', '明镜'],
      ['current_life', '正在准备面试'],
      ['priorities', '希望留出学习时间'],
      ['directness', '直说'],
      ['terminology', '术语少一点'],
      ['answer_length', '短一点'],
      ['outreach', '可以'],
    ];
    for (const [step, value] of answers) {
      if (controller.getSnapshot().step === 'birth') controller.skip();
      expect(controller.getSnapshot().step).toBe(step);
      await controller.submit(value);
    }
    const summary = controller.getSnapshot();
    expect(summary.step).toBe('summary');
    expect(summary.stage).toBe(7);
    for (const text of ['小远', '正在准备面试', '学习时间', '直说', '术语少一点', '短一点', '可以', '待真实排盘计算'])
      expect(summary.prompt.text).toContain(text);
    expect(summary.prompt.text).not.toMatch(/birth\.|00:00|出生地点/);
    expect(aboutMe.getSnapshot().profileItems.filter((item) => item.id.startsWith('onboarding-'))).toHaveLength(8);
    controller.continue();
    expect(controller.getSnapshot()).toMatchObject({ step: 'done', status: 'complete' });
  });
  it('skips only explicit known slots and never infers birth confirmation or known names from Q3 text', () => {
    const { controller } = setup();
    controller.start('known');
    controller.continue();
    expect(controller.getSnapshot().step).toBe('birth');
    controller.skip();
    expect(controller.getSnapshot().step).toBe('current_life');
    controller.start('new');
    controller.continue();
    expect(controller.getSnapshot().step).toBe('user_name');
  });
  it('pauses on natural language without saving it and resumes the same question and draft', async () => {
    const { controller, aboutMe } = setup();
    controller.start();
    controller.continue();
    controller.setDraft('原来的称呼草稿');
    await controller.submit('先到这里');
    expect(controller.getSnapshot()).toMatchObject({ status: 'paused', step: 'user_name', draft: '原来的称呼草稿' });
    expect(aboutMe.getSnapshot().revision).toBe(1);
    controller.resume();
    expect(controller.getSnapshot().status).toBe('active');
  });
  it('reuses the exact operation after an ambiguous response and does not advance before acknowledgement', async () => {
    const { aboutMe, birth } = setup(),
      execute = vi.fn(aboutMe.execute);
    execute.mockRejectedValueOnce(new Error('network'));
    const controller = createOnboardingController({ aboutMe: { ...aboutMe, execute }, birth });
    controller.start();
    controller.continue();
    await controller.submit('小远');
    expect(controller.getSnapshot().step).toBe('user_name');
    expect(controller.getSnapshot().hasPending).toBe(true);
    controller.setDraft('不能覆盖原提交');
    expect(controller.getSnapshot().draft).toBe('小远');
    await controller.submit('不同答案');
    expect(execute).toHaveBeenCalledTimes(1);
    await controller.submit('小远');
    expect(execute.mock.calls[0][0]).toBe(execute.mock.calls[1][0]);
    expect(controller.getSnapshot().step).toBe('assistant_name');
    expect(controller.getSnapshot().hasPending).toBe(false);
  });
  it('locks after CAS conflict and preserves the draft until explicit reread and reconfirmation', async () => {
    const { aboutMe, birth } = setup();
    let first = true;
    const execute = vi.fn(async (command: AboutMeCommand) => {
      if (first) {
        first = false;
        throw { status: 409, message: 'conflict' };
      }
      return aboutMe.execute(command);
    });
    const controller = createOnboardingController({ aboutMe: { ...aboutMe, execute }, birth });
    controller.start();
    controller.continue();
    await controller.submit('小远');
    expect(controller.getSnapshot()).toMatchObject({ conflicted: true, draft: '小远', step: 'user_name' });
    await controller.submit('小远');
    expect(execute).toHaveBeenCalledTimes(1);
    controller.reconcile();
    await controller.submit('小远');
    expect(execute.mock.calls[0][0].requestId).not.toBe(execute.mock.calls[1][0].requestId);
    expect(controller.getSnapshot().step).toBe('assistant_name');
  });
  it('ignores a delayed acknowledgement after pause and safely retries the committed operation', async () => {
    const { aboutMe, birth } = setup();
    let release: () => void = () => undefined;
    const execute = vi.fn(async (command: AboutMeCommand) => {
      const ack = await aboutMe.execute(command);
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      return ack;
    });
    const controller = createOnboardingController({ aboutMe: { ...aboutMe, execute }, birth });
    controller.start();
    controller.continue();
    const pending = controller.submit('小远');
    await Promise.resolve();
    controller.pause();
    release();
    await pending;
    expect(controller.getSnapshot()).toMatchObject({ status: 'paused', step: 'user_name', busy: false });
    expect(controller.getSnapshot().messages.some((item) => item.role === 'user')).toBe(false);
  });
  it('accepts only a real redacted birth receipt without copying raw fields into profile or messages', async () => {
    const { controller, aboutMe, birth } = setup();
    controller.start('known');
    controller.continue();
    expect(
      controller.birthConfirmed({
        requestId: 'fake',
        kind: 'birth-confirm',
        write_status: 'saved',
        revision: 1,
        confirmation: 'partial',
        confirmedFields: ['date'],
      }),
    ).toBe(false);
    const receipt = await birth.confirm({
      requestId: 'birth',
      expectedRevision: 0,
      confirmed: true,
      draft: { ...emptyBirthDraft(), date: '1998-03-12' },
    });
    expect(controller.birthConfirmed(receipt)).toBe(true);
    expect(controller.getSnapshot().step).toBe('current_life');
    expect(JSON.stringify(controller.getSnapshot())).not.toContain('1998-03-12');
    expect(JSON.stringify(aboutMe.getSnapshot())).not.toContain('1998-03-12');
  });
  it('takes a separate outreach time subturn and keeps all settings explicitly local', async () => {
    const { controller } = setup();
    controller.start('known');
    controller.continue();
    controller.skip();
    controller.skip();
    controller.skip();
    expect(controller.getSnapshot().step).toBe('outreach');
    await controller.submit('晨报换个时间');
    expect(controller.getSnapshot().step).toBe('outreach_time');
    await controller.submit('25:99');
    expect(controller.getSnapshot().step).toBe('outreach_time');
    await controller.submit('09:30');
    expect(controller.getSnapshot().prompt.text).toContain('09:30');
    expect(controller.getSnapshot().prompt.text).toContain('真实投递尚未启用');
  });
});
