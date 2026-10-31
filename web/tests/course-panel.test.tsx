import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { act, render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import CoursePanel from '../src/study/courses/CoursePanel';
import { readCourse } from '../src/study/courses/readCourse';
import type { CourseData } from '../src/study/courses/types';
import type { CourseLoader } from '../src/study/courses/loader';

const data = readCourse(JSON.parse(readFileSync(resolve('public/data/study/courses-v5/course.json'), 'utf8')));
const loader = () => vi.fn<CourseLoader>().mockResolvedValue(structuredClone(data));
const lesson = () => screen.getByRole('article', { name: '第1课 四柱先按位置读' });
const directory = () => screen.getByRole('navigation', { name: '课程目录' });
function gate() {
  let resolve!: (value: CourseData) => void;
  const promise = new Promise<CourseData>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('twenty course lessons, local practice only', () => {
  it('does not load a hidden unopened course and does not refetch when revisiting ready data', async () => {
    const load = loader(),
      view = render(<CoursePanel active={false} loader={load} />);
    expect(load).not.toHaveBeenCalled();
    view.rerender(<CoursePanel active loader={load} />);
    await screen.findByRole('navigation', { name: '课程目录' });
    expect(within(directory()).getAllByRole('button')).toHaveLength(20);
    view.rerender(<CoursePanel active={false} loader={load} />);
    view.rerender(<CoursePanel active loader={load} />);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it('selects a lesson by keyboard, moves reading focus, and keeps previous/next bounds', async () => {
    render(<CoursePanel active loader={loader()} />);
    await screen.findByRole('navigation', { name: '课程目录' });
    expect(screen.getByRole('button', { name: '上一课' })).toBeDisabled();
    const last = within(directory()).getAllByRole('button')[19];
    last.focus();
    await userEvent.keyboard('{Enter}');
    expect(screen.getByRole('heading', { name: data.lessons[19].title })).toHaveFocus();
    expect(screen.getByRole('button', { name: '下一课' })).toBeDisabled();
    expect(last).toHaveAttribute('aria-current', 'step');
    await userEvent.click(screen.getByRole('button', { name: '上一课' }));
    expect(screen.getByRole('heading', { name: data.lessons[18].title })).toHaveFocus();
  });

  it('checks stable answer IDs, retains choices while paging, and never persists progress', async () => {
    const writes = vi.spyOn(Storage.prototype, 'setItem'),
      fetcher = vi.spyOn(globalThis, 'fetch');
    render(<CoursePanel active loader={loader()} />);
    await screen.findByRole('navigation', { name: '课程目录' });
    for (const quiz of data.lessons[0].quiz) {
      const field = lesson().querySelector(`[data-course-quiz="${quiz.quiz_id}"]`)! as HTMLElement;
      expect(within(field).getByRole('button', { name: '核对这题' })).toBeDisabled();
      const correct = quiz.options.find((row) => row.option_id === quiz.correct_option_id)!;
      await userEvent.click(within(field).getByRole('radio', { name: correct.text }));
      await userEvent.click(within(field).getByRole('button', { name: '核对这题' }));
    }
    expect(screen.getByText(/本页练习：1\/20课已核对/)).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '下一课' }));
    await userEvent.click(screen.getByRole('button', { name: '上一课' }));
    expect(
      within(lesson())
        .getAllByRole('radio')
        .filter((node) => (node as HTMLInputElement).checked),
    ).toHaveLength(2);
    expect(within(lesson()).getAllByText('这题已核对。')).toHaveLength(2);
    expect(writes).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '清空本页练习' }));
    expect(screen.getByText(/本页练习：0\/20课已核对/)).toBeVisible();
    expect(
      within(lesson())
        .getAllByRole('radio')
        .every((node) => !(node as HTMLInputElement).checked),
    ).toBe(true);
  });

  it('does not count a wrong answer and invalidates checked state after editing an answer', async () => {
    render(<CoursePanel active loader={loader()} />);
    await screen.findByRole('navigation', { name: '课程目录' });
    const field = lesson().querySelector('[data-course-quiz="lesson-01-q1"]')! as HTMLElement;
    await userEvent.click(within(field).getByRole('radio', { name: '丁酉' }));
    await userEvent.click(within(field).getByRole('button', { name: '核对这题' }));
    expect(within(field).getByText('再读一下依据，可以重新选择。')).toBeVisible();
    await userEvent.click(within(field).getByRole('radio', { name: '甲戌' }));
    expect(within(field).queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByText(/本页练习：0\/20课已核对/)).toBeVisible();
  });

  it('marks completion explicitly and keeps a per-lesson bookmark in the synthetic progress port', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch'),
      writes = vi.spyOn(Storage.prototype, 'setItem');
    render(<CoursePanel active loader={loader()} />);
    await screen.findByRole('navigation', { name: '课程目录' });
    expect(screen.getByText('继续学习。')).toBeVisible();
    await userEvent.type(screen.getByRole('textbox', { name: '本课书签' }), '第二段');
    await userEvent.click(screen.getByRole('button', { name: '标记本课完成' }));
    expect(await screen.findByText('已按你的标记记录完成；不代表理解或评测通过。')).toBeVisible();
    expect(screen.getByText(/你已标记完成。/)).toBeVisible();
    expect(screen.getByText(/当前书签：第二段/)).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '下一课' }));
    expect(screen.getByText('继续学习。')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '上一课' }));
    expect(screen.getByText(/你已标记完成。/)).toBeVisible();
    expect(screen.getByRole('textbox', { name: '本课书签' })).toHaveValue('第二段');
    expect(screen.getByText(/本页练习：0\/20课已核对/)).toBeVisible();
    expect(fetcher).not.toHaveBeenCalled();
    expect(writes).not.toHaveBeenCalled();
  });

  it('shows independent c7 case basis and original source caveats on the last lesson', async () => {
    render(<CoursePanel active loader={loader()} />);
    await screen.findByRole('navigation', { name: '课程目录' });
    await userEvent.click(within(directory()).getAllByRole('button')[19]);
    await userEvent.click(screen.getByText('本课依据与口径', { selector: 'summary' }));
    expect(screen.getByText('阿远 · 西方占星 · 〔c7〕')).toBeVisible();
    expect(screen.getByText(/不与旧版学习卡按短号合并/)).toBeVisible();
    await userEvent.click(screen.getByText('出处、流派差异与待核项', { selector: 'summary' }));
    expect(screen.getByRole('heading', { name: '仍待核对' })).toBeVisible();
  });

  it('ignores late loads after hiding or unmounting, then can retry current ownership', async () => {
    const first = gate(),
      second = gate();
    const load = vi.fn<CourseLoader>().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const view = render(<CoursePanel active loader={load} />);
    view.rerender(<CoursePanel active={false} loader={load} />);
    expect(load.mock.calls[0][0].aborted).toBe(true);
    await act(async () => first.resolve(data));
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    view.rerender(<CoursePanel active loader={load} />);
    await act(async () => second.resolve(data));
    await screen.findByRole('navigation', { name: '课程目录' });
    view.unmount();
    expect(load.mock.calls[1][0].aborted).toBe(true);
  });

  it('redacts read failures and retries without displaying low-level details', async () => {
    const load = loader().mockRejectedValueOnce(new Error('SECRET_FAILURE'));
    render(<CoursePanel active loader={load} />);
    expect(await screen.findByRole('alert')).not.toHaveTextContent('SECRET_FAILURE');
    await userEvent.click(screen.getByRole('button', { name: '重新读取课程' }));
    await waitFor(() => expect(directory()).toBeVisible());
    expect(load).toHaveBeenCalledTimes(2);
  });
});
