import { publicChatText } from '../../chat/publicProjection';
import { Button, Textarea } from '../../components/ui/Controls';
import type { OnboardingController, OnboardingSnapshot } from './types';

export function GuidedQuestion({ state, controller }: { state: OnboardingSnapshot; controller: OnboardingController }) {
  const disabled = state.busy || state.conflicted || state.status !== 'active';
  return (
    <section className="live-ask-card onboarding-question" aria-label="相识这轮问题">
      <h2>{publicChatText(state.prompt.text)}</h2>
      <p className="meta">为什么问：{publicChatText(state.prompt.why)}</p>
      {!!state.prompt.options.length && (
        <div className="stack small">
          {state.prompt.options.map((option) => (
            <Button
              key={option}
              disabled={disabled || (state.hasPending && state.draft !== option)}
              onClick={() => void controller.submit(option)}>
              {publicChatText(option)}
            </Button>
          ))}
          <Button
            variant="ghost"
            disabled={disabled || state.hasPending}
            onClick={() => document.getElementById('onboarding-answer')?.focus()}>
            我自己说
          </Button>
        </div>
      )}
      <form
        className="stack small onboarding-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void controller.submit();
        }}>
        <label className="field">
          相识这轮回答
          <Textarea
            id="onboarding-answer"
            aria-label="相识这轮回答"
            rows={2}
            value={state.draft}
            disabled={disabled || state.hasPending}
            onChange={(event) => controller.setDraft(event.target.value)}
          />
        </label>
        <div className="row wrap">
          <Button type="submit" disabled={disabled || !state.draft.trim()} loading={state.busy}>
            {state.hasPending ? '重试原回答' : '发送回答'}
          </Button>
          <Button variant="ghost" disabled={disabled || state.hasPending} onClick={controller.skip}>
            暂时跳过
          </Button>
        </div>
      </form>
    </section>
  );
}
