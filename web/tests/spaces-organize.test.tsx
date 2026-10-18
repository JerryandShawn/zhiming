import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrganizePage from '../src/spaces/OrganizePage';
import { useSpacesDemo } from '../src/spaces/store';

const card = (title: string) => screen.getByRole('article', { name: `话题：${title}` });
const topic = (id: string) => useSpacesDemo.getState().draft.topics.find((row) => row.id === id)!;
const originals = () =>
  useSpacesDemo.getState().data.messages.map(({ id, text, at, role }) => ({ id, text, at, role }));
async function editTopic(title: string, command: string) {
  await userEvent.click(within(card(title)).getByRole('button', { name: command }));
}
async function nameAndSave(name: string, label = '名称') {
  const field = screen.getByRole('textbox', { name: label });
  await userEvent.clear(field);
  await userEvent.type(field, name);
  await userEvent.click(screen.getByRole('button', { name: '保存到草稿' }));
}

describe('local organize proposal editing', () => {
  beforeEach(() => {
    useSpacesDemo.getState().reset();
    // These existing edit contracts exercise the unchanged five-button desktop layout.
    vi.mocked(window.matchMedia).mockImplementation((query) => ({
      matches: query === '(min-width: 1024px)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  it('shows synthetic scope, counts, low confidence in text and sensitive locks', () => {
    render(<OrganizePage />);
    expect(screen.getByText('合成数据 · 本地模拟')).toBeVisible();
    expect(screen.getByText(/不能整理真实旧聊天/)).toBeVisible();
    expect(screen.getByRole('heading', { level: 2, name: '整理草稿区与话题' })).toBeInTheDocument();
    expect(within(card('周末散步')).getByRole('heading', { level: 3, name: '周末散步' })).toBeVisible();
    expect(screen.getAllByLabelText('敏感区')).toHaveLength(2);
    expect(screen.getByText('待你确认 · 把握度低')).toBeVisible();
    expect(within(card('跳槽 · 面试')).getByText(/4 条消息/)).toBeVisible();
    expect(screen.getByRole('button', { name: '让明镜帮我起标题' })).toBeDisabled();
  });

  it('renames spaces and topics in draft without changing the applied dataset', async () => {
    const before = structuredClone(useSpacesDemo.getState().data);
    render(<OrganizePage />);
    await userEvent.click(screen.getByRole('button', { name: '改区名：事业学业' }));
    await nameAndSave('成长');
    expect(useSpacesDemo.getState().draft.spaces.find((row) => row.id === 'career')?.name).toBe('成长');
    await editTopic('跳槽 · 面试', '改名');
    await nameAndSave('面试准备');
    expect(topic('interview').title).toBe('面试准备');
    expect(useSpacesDemo.getState().data).toEqual(before);
  });

  it('merges explicitly into another topic and preserves every original message', async () => {
    const before = originals();
    render(<OrganizePage />);
    await editTopic('跳槽 · 面试', '合并');
    expect(screen.getByText(/把“跳槽 · 面试”并入所选话题/)).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '保存到草稿' }));
    expect(topic('skills').messageIds).toEqual(expect.arrayContaining(['i1', 'i2', 'i3', 'i4']));
    expect(useSpacesDemo.getState().draft.topics.some((row) => row.id === 'interview')).toBe(false);
    expect(originals()).toEqual(before);
  });

  it('splits only selected original messages into the named new topic', async () => {
    const before = originals();
    render(<OrganizePage />);
    await editTopic('跳槽 · 面试', '拆分');
    const choices = screen.getAllByRole('checkbox');
    await userEvent.click(choices[2]);
    await userEvent.click(choices[3]);
    await nameAndSave('协作练习', '新话题名称');
    expect(topic('interview').messageIds).toEqual(['i1', 'i2']);
    expect(useSpacesDemo.getState().draft.topics.find((row) => row.title === '协作练习')?.messageIds).toEqual([
      'i3',
      'i4',
    ]);
    expect(originals()).toEqual(before);
  });

  it('moves and ignores a topic while preserving originals, then resets the draft', async () => {
    const before = structuredClone(useSpacesDemo.getState().data);
    render(<OrganizePage />);
    await editTopic('跳槽 · 面试', '移动');
    await userEvent.click(screen.getByRole('combobox', { name: '移到哪个区' }));
    await userEvent.click(screen.getByRole('option', { name: '家庭' }));
    await userEvent.click(screen.getByRole('button', { name: '保存到草稿' }));
    expect(topic('interview').spaceId).toBe('family');
    await userEvent.click(within(card('跳槽 · 面试')).getByRole('button', { name: '忽略本批' }));
    expect(useSpacesDemo.getState().draft.ignoredTopicIds).toContain('interview');
    expect(screen.getByRole('region', { name: '本批忽略的话题' })).toHaveTextContent('跳槽 · 面试');
    expect(useSpacesDemo.getState().data).toEqual(before);
    await userEvent.click(screen.getByRole('button', { name: '重置草稿' }));
    expect(topic('interview').spaceId).toBe('career');
    expect(useSpacesDemo.getState().draft.ignoredTopicIds).toEqual([]);
  });

  it('keeps empty names and invalid split selections in the open editor', async () => {
    const before = structuredClone(useSpacesDemo.getState().draft);
    render(<OrganizePage />);
    await editTopic('跳槽 · 面试', '改名');
    await userEvent.clear(screen.getByRole('textbox', { name: '名称' }));
    await userEvent.click(screen.getByRole('button', { name: '保存到草稿' }));
    expect(screen.getByRole('alert')).toHaveTextContent('名称要有 1–60 个字');
    expect(screen.getByRole('dialog')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(within(card('跳槽 · 面试')).getByRole('button', { name: '改名' })).toHaveFocus();
    await editTopic('跳槽 · 面试', '拆分');
    await nameAndSave('不合法拆分', '新话题名称');
    expect(screen.getByRole('alert')).not.toBeEmptyDOMElement();
    expect(screen.getByRole('dialog')).toBeVisible();
    expect(useSpacesDemo.getState().draft).toEqual(before);
  });

  it('requires apply and revert confirmations and round-trips all original fields', async () => {
    const before = structuredClone(useSpacesDemo.getState().data);
    const rawBefore = originals();
    render(<OrganizePage />);
    await editTopic('跳槽 · 面试', '改名');
    await nameAndSave('面试准备');
    await userEvent.click(screen.getByRole('button', { name: '应用整理' }));
    await userEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(useSpacesDemo.getState().data).toEqual(before);
    expect(useSpacesDemo.getState().applied).toBeUndefined();
    await userEvent.click(screen.getByRole('button', { name: '应用整理' }));
    await userEvent.click(screen.getByRole('button', { name: '确认应用演示整理' }));
    expect(useSpacesDemo.getState().data.topics.find((row) => row.id === 'interview')?.title).toBe('面试准备');
    expect(useSpacesDemo.getState().applied?.batchId).toMatch(/demo/);
    expect(originals()).toEqual(rawBefore);
    await userEvent.click(screen.getByRole('button', { name: '撤销本批整理' }));
    await userEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(useSpacesDemo.getState().applied).toBeDefined();
    await userEvent.click(screen.getByRole('button', { name: '撤销本批整理' }));
    await userEvent.click(screen.getByRole('button', { name: '确认撤销演示整理' }));
    expect(useSpacesDemo.getState().data).toEqual(before);
    expect(useSpacesDemo.getState().applied).toBeUndefined();
  });

  it('keeps a failed local apply confirmation open and makes the failure visible', async () => {
    render(<OrganizePage />);
    act(() => useSpacesDemo.setState({ draft: { ...useSpacesDemo.getState().draft, topics: [] } }));
    await userEvent.click(screen.getByRole('button', { name: '应用整理' }));
    await userEvent.click(screen.getByRole('button', { name: '确认应用演示整理' }));
    expect(screen.getByRole('dialog')).toBeVisible();
    expect(within(screen.getByRole('dialog')).getByRole('alert')).not.toBeEmptyDOMElement();
    expect(useSpacesDemo.getState().applied).toBeUndefined();
  });
});
