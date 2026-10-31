import { afterEach, describe, expect, it, vi } from 'vitest';
import { createNightPort } from '../src/night/port';
import { createAboutMeStore } from '../src/night/me/port';
import { createAboutMeSeed } from '../src/night/me/fixtures';
import { PROFILE_SECTIONS, type AboutMeCommand } from '../src/night/me/types';

afterEach(() => vi.restoreAllMocks());
const pending = {
  proposal_id: 'local-proposal',
  write_status: 'pending_confirmation',
  summary: '希望跟进一项健康安排（合成示例）',
  category: 'health',
  revision: 1,
};
const saved = {
  fact_id: 'local-preference',
  write_status: 'saved',
  summary: '偏好先看简短结论（合成示例）',
  revision: 1,
};

describe('About Me shared aggregate', () => {
  it('seeds the eight canonical profile sections and shares both fixed chat IDs', () => {
    const port = createNightPort(),
      snapshot = port.aboutMe.getSnapshot();
    expect(snapshot.profileItems.map((item) => item.section)).toEqual(PROFILE_SECTIONS.map((section) => section.id));
    expect(snapshot.memories).toHaveLength(8);
    expect(snapshot.proposals.filter((item) => item.status === 'pending')).toHaveLength(3);
    expect(port.memory).toBe(port.aboutMe.memory);
    expect(port.currentReceipts()).toContainEqual(expect.objectContaining(saved));
    expect(port.currentReceipts()).toContainEqual(expect.objectContaining(pending));
    expect(snapshot).not.toHaveProperty('sources');
    expect(snapshot).not.toHaveProperty('revokedFactIds');
  });

  it('keeps snapshot references stable during reads and commits an immutable revision once', async () => {
    const port = createAboutMeStore(),
      first = port.getSnapshot(),
      listener = vi.fn();
    const unsubscribe = port.subscribe(listener);
    port.previewDelete('memory-basic', 'fact');
    port.readSource(first.memories[0].sourceRefs[0]);
    expect(port.getSnapshot()).toBe(first);
    expect(listener).not.toHaveBeenCalled();
    expect(() => first.memories.push(first.memories[0])).toThrow();
    await port.execute({
      type: 'profile-delete',
      id: 'profile-goals',
      expectedRevision: 1,
      requestId: 'delete-profile',
    });
    expect(port.getSnapshot()).not.toBe(first);
    expect(port.getSnapshot().revision).toBe(2);
    expect(first.profileItems.find((item) => item.id === 'profile-goals')?.status).toBe('active');
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it('creates a user correction source and fact before marking a profile entry as user edited', async () => {
    const port = createAboutMeStore();
    const result = await port.execute({
      type: 'profile-edit',
      id: 'profile-basic',
      expectedRevision: 1,
      requestId: 'profile-edit',
      text: '请叫我小远，正在学习交互设计。',
    });
    const snapshot = port.getSnapshot(),
      item = snapshot.profileItems.find((row) => row.id === 'profile-basic')!;
    expect(item).toMatchObject({ text: '请叫我小远，正在学习交互设计。', userEdited: true, revision: 2 });
    expect(item.factIds).toEqual([result.factId]);
    expect(item.sourceIds).toEqual([result.sourceId]);
    const fact = snapshot.memories.find((row) => row.id === result.factId)!;
    expect(fact.text).toBe(item.text);
    expect(fact.sourceRefs[0].channel).toBe('web-action');
    expect(port.readSource(fact.sourceRefs[0])).toMatchObject({ available: true, quote: item.text });
    expect(snapshot.memories.find((row) => row.id === 'memory-basic')?.status).toBe('active');
    expect(result.memoryReceipt?.fact_id).toBe(fact.id);
  });

  it('returns the same receipt for an identical operation and rejects changed payloads or action reuse', async () => {
    const port = createAboutMeStore(),
      listener = vi.fn();
    port.subscribe(listener);
    const command: AboutMeCommand = {
      type: 'profile-edit',
      id: 'profile-goals',
      expectedRevision: 1,
      requestId: 'same-operation',
      text: '想每周留两晚学习。',
    };
    const result = await port.execute(command);
    expect(await port.execute({ ...command })).toBe(result);
    await expect(port.execute({ ...command, text: '换了正文' })).rejects.toMatchObject({
      code: 'REPLAY_CHANGED',
      status: 409,
    });
    await expect(
      port.execute({ type: 'profile-delete', id: command.id, expectedRevision: 1, requestId: command.requestId }),
    ).rejects.toMatchObject({ code: 'REPLAY_CHANGED' });
    expect(port.getSnapshot().revision).toBe(2);
    expect(port.getSnapshot().memories).toHaveLength(9);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('rejects a stale concurrent edit without mutating the successful user correction', async () => {
    const port = createAboutMeStore();
    await port.execute({
      type: 'profile-edit',
      id: 'profile-goals',
      expectedRevision: 1,
      requestId: 'first-edit',
      text: '周末想留时间休息。',
    });
    const before = port.getSnapshot();
    await expect(
      port.execute({
        type: 'profile-edit',
        id: 'profile-goals',
        expectedRevision: 1,
        requestId: 'stale-edit',
        text: '另一个草稿',
      }),
    ).rejects.toMatchObject({ status: 409 });
    expect(port.getSnapshot()).toBe(before);
    expect(before.profileItems.find((item) => item.id === 'profile-goals')?.text).toBe('周末想留时间休息。');
  });

  it('deletes only a profile entry and leaves its underlying fact and source available', async () => {
    const port = createAboutMeStore(),
      fact = port.getSnapshot().memories[0];
    await port.execute({ type: 'profile-delete', id: 'profile-basic', expectedRevision: 1, requestId: 'profile-only' });
    expect(port.getSnapshot().profileItems.find((item) => item.id === 'profile-basic')?.status).toBe('deleted');
    expect(port.getSnapshot().memories.find((item) => item.id === fact.id)).toEqual(fact);
    expect(port.readSource(fact.sourceRefs[0]).available).toBe(true);
  });

  it.each(['', 'x'.repeat(2001), 'birth.solar_datetime: PRIVATE', '出生地点：PRIVATE'])(
    'rejects invalid or raw birth profile edits atomically: %s',
    async (text) => {
      const port = createAboutMeStore(),
        before = port.getSnapshot();
      await expect(
        port.execute({
          type: 'profile-edit',
          id: 'profile-chart_summary',
          expectedRevision: 1,
          requestId: 'invalid',
          text,
        }),
      ).rejects.toMatchObject({ status: 422 });
      expect(port.getSnapshot()).toBe(before);
      expect(before.profileItems.some((item) => item.userEdited)).toBe(false);
    },
  );

  it('accepts an empty profile seed and saves new canonical sections using the same edit command', async () => {
    const seed = createAboutMeSeed();
    seed.profileItems = [];
    const port = createAboutMeStore(seed, () => '2026-10-19T04:00:00+08:00');
    await port.execute({
      type: 'profile-edit',
      id: 'profile-basic',
      section: 'basic',
      expectedRevision: 0,
      requestId: 'new-item',
      text: '请叫我小林。',
    });
    expect(seed.profileItems).toEqual([]);
    expect(port.getSnapshot().profileItems).toHaveLength(1);
    expect(port.getSnapshot().profileItems[0]).toMatchObject({ section: 'basic', revision: 1, userEdited: true });
    expect(port.getSnapshot().profileItems[0].updatedAt).toBe('2026-10-19T04:00:00+08:00');
  });

  it('corrects a memory through a new user source and invalidates its old derived profile', async () => {
    const port = createAboutMeStore();
    const result = await port.execute({
      type: 'memory-edit',
      id: 'memory-basic',
      expectedRevision: 1,
      requestId: 'memory-correction',
      text: '请叫我林同学。',
    });
    const item = port.getSnapshot().memories.find((row) => row.id === 'memory-basic')!;
    expect(item).toMatchObject({ text: '请叫我林同学。', revision: 2 });
    expect(port.readSource(item.sourceRefs[0])).toMatchObject({ available: true, quote: item.text });
    expect(result.affectedIds).toContain('profile-basic');
    expect(port.getSnapshot().profileItems.find((row) => row.id === 'profile-basic')?.status).toBe('deleted');
    expect(port.getSnapshot().memories.find((row) => row.id === 'memory-life')?.status).toBe('active');
  });

  it('shares Chat confirmation, About Me state and higher-revision withdrawal receipts', async () => {
    const port = createNightPort();
    const result = await port.memory.execute('remember', pending);
    expect(port.aboutMe.getSnapshot().proposals.find((item) => item.id === pending.proposal_id)?.status).toBe('saved');
    const fact = port.aboutMe.getSnapshot().memories.find((item) => item.id === result.fact_id)!;
    expect(fact).toMatchObject({ revision: 2, status: 'active', proposalId: pending.proposal_id });
    await port.aboutMe.execute({ type: 'memory-stop', id: fact.id, expectedRevision: 2, requestId: 'me-withdrawal' });
    expect(port.currentReceipts()).toContainEqual(
      expect.objectContaining({
        fact_id: fact.id,
        proposal_id: pending.proposal_id,
        write_status: 'stopped',
        revision: 3,
      }),
    );
    expect(port.memory.supports('undo', { ...pending, ...result, summary: pending.summary })).toBe(false);
    expect(await port.memory.execute('remember', pending)).toBe(result);
    expect(port.currentReceipts().find((item) => item.fact_id === fact.id)?.write_status).toBe('stopped');
  });

  it('lets About Me confirm a proposal and Chat undo that very same fact', async () => {
    const port = createNightPort();
    await port.aboutMe.execute({
      type: 'proposal-act',
      action: 'remember',
      id: pending.proposal_id,
      expectedRevision: 1,
      requestId: 'me-confirm',
    });
    const receipt = port.currentReceipts().find((item) => item.proposal_id === pending.proposal_id)!;
    expect(port.memory.supports('undo', receipt)).toBe(true);
    await port.memory.execute('undo', receipt);
    expect(port.aboutMe.getSnapshot().memories.find((item) => item.id === receipt.fact_id)?.status).toBe('stopped');
  });

  it('updates one shared category preference only after an exact confirmed command', async () => {
    const port = createNightPort();
    const result = await port.memory.execute('remember-category', pending);
    expect(result).toMatchObject({ write_status: 'saved', category_saved: true, category: 'health' });
    expect(port.aboutMe.getSnapshot().autoSaveCategories).toEqual(['health']);
    expect([...port.autoSaveCategories]).toEqual(['health']);
    (port.autoSaveCategories as Set<string>).add('cannot-change-store');
    expect(port.aboutMe.getSnapshot().autoSaveCategories).toEqual(['health']);
    await expect(port.memory.execute('remember-category', { ...pending, category: 'finance' })).rejects.toMatchObject({
      code: 'REPLAY_CHANGED',
    });
    await expect(port.memory.execute('remember-category', { ...pending, summary: 'changed' })).rejects.toMatchObject({
      code: 'REPLAY_CHANGED',
    });
  });

  it('turns an unanchored legacy note into a new explicit user confirmation source', async () => {
    const port = createAboutMeStore();
    const result = await port.execute({
      type: 'proposal-act',
      id: 'legacy-note',
      action: 'remember',
      expectedRevision: 1,
      requestId: 'legacy-confirm',
    });
    const fact = port.getSnapshot().memories.find((item) => item.id === result.factId)!;
    expect(fact.sourceRefs).toHaveLength(1);
    expect(fact.sourceRefs[0].channel).toBe('web-action');
    expect(port.readSource(fact.sourceRefs[0]).label).toContain('本次用户编辑或确认');
  });

  it('never creates unknown proposals, or grants a category preference without a category', async () => {
    const port = createNightPort(),
      unknown = { ...pending, proposal_id: 'unknown' };
    expect(port.memory.supports('remember', unknown)).toBe(false);
    await expect(port.memory.execute('remember', unknown)).rejects.toMatchObject({ status: 404 });
    await expect(
      port.aboutMe.execute({
        type: 'proposal-act',
        id: 'legacy-note',
        action: 'remember-category',
        expectedRevision: 1,
        requestId: 'no-category',
      }),
    ).rejects.toMatchObject({ status: 422 });
    expect(port.aboutMe.getSnapshot().revision).toBe(1);
  });

  it('derives people and timeline only from active facts and supports dictionary entry deletion', async () => {
    const port = createAboutMeStore();
    await port.execute({ type: 'memory-stop', id: 'memory-people', expectedRevision: 1, requestId: 'stop-person' });
    expect(port.getSnapshot().people).toEqual([]);
    await port.execute({ type: 'memory-stop', id: 'memory-followup', expectedRevision: 1, requestId: 'stop-event' });
    expect(port.getSnapshot().timeline).toEqual([]);
    const result = await port.execute({
      type: 'symbol-delete',
      id: 'symbol-star',
      expectedRevision: 1,
      requestId: 'delete-symbol',
    });
    expect(result.write_status).toBe('deleted');
    expect(port.getSnapshot().dictionary[0].status).toBe('deleted');
  });

  it('uses no network, credentials or persistent storage for construction, reads and writes', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch'),
      get = vi.spyOn(Storage.prototype, 'getItem'),
      set = vi.spyOn(Storage.prototype, 'setItem');
    const port = createNightPort();
    port.aboutMe.getSnapshot();
    port.currentReceipts();
    await port.memory.execute('undo', saved);
    await port.answer('先试试', 'local-answer');
    expect(fetcher).not.toHaveBeenCalled();
    expect(get).not.toHaveBeenCalled();
    expect(set).not.toHaveBeenCalled();
  });
});
