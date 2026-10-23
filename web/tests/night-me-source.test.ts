import { describe, expect, it } from 'vitest';
import { createAboutMeStore } from '../src/night/me/port';
import { createAboutMeSeed } from '../src/night/me/fixtures';
import { createNightPort } from '../src/night/port';

describe('About Me source authorization and deletion scope', () => {
  it('returns only an authorized continuous quote, never the whole source body', () => {
    const port = createAboutMeStore(),
      ref = port.getSnapshot().memories[0].sourceRefs[0];
    const result = port.readSource(ref);
    expect(result).toMatchObject({ available: true, quote: '请叫我阿远，目前在学习产品设计。' });
    expect(JSON.stringify(result)).not.toContain('这句未授权节选不应整段展示');
    expect(result).not.toHaveProperty('content');
    expect(JSON.stringify(port.getSnapshot())).not.toContain('这句未授权节选不应整段展示');
    expect(port.readSource({ ...ref, start: 0, end: 10000, quote: '伪造原话' })).toMatchObject({
      available: false,
      ref: { quote: '' },
    });
    expect(port.readSource({ ...ref, version: 99 })).not.toHaveProperty('quote');
  });

  it('deletes just one fact and its derived profile while retaining its original source and sibling fact', async () => {
    const port = createAboutMeStore(),
      before = port.getSnapshot();
    const preview = port.previewDelete('memory-basic', 'fact');
    expect(preview.counts).toEqual({ memories: 1, profileItems: 1, proposals: 0, symbols: 0 });
    await port.execute({
      type: 'memory-delete',
      id: preview.targetId,
      scope: preview.scope,
      expectedRevision: preview.targetRevision,
      expectedSnapshotRevision: preview.snapshotRevision,
      requestId: 'fact-only',
    });
    const after = port.getSnapshot();
    expect(after.memories.find((item) => item.id === 'memory-basic')).toMatchObject({
      status: 'deleted',
      text: '',
      sourceRefs: [],
      revision: 2,
    });
    expect(after.profileItems.find((item) => item.id === 'profile-basic')?.status).toBe('deleted');
    expect(after.memories.find((item) => item.id === 'memory-life')).toEqual(
      before.memories.find((item) => item.id === 'memory-life'),
    );
    expect(after.proposals.find((item) => item.id === 'local-proposal-career')?.status).toBe('pending');
    expect(port.readSource(after.memories.find((item) => item.id === 'memory-life')!.sourceRefs[0]).available).toBe(
      true,
    );
    expect(port.readSource(before.memories[0].sourceRefs[0]).available).toBe(false);
  });

  it('cascades one exact messageId to its facts, profiles and proposals and leaves every unrelated ID unchanged', async () => {
    const port = createAboutMeStore(),
      before = port.getSnapshot();
    const preview = port.previewDelete('memory-basic', 'source', before.memories[0].sourceRefs[0]);
    expect([...preview.affectedFactIds].sort()).toEqual(['memory-basic', 'memory-life']);
    expect([...preview.affectedProfileIds].sort()).toEqual(['profile-basic', 'profile-current_life']);
    expect(preview.affectedProposalIds).toEqual(['local-proposal-career']);
    const receipt = await port.execute({
      type: 'memory-delete',
      id: preview.targetId,
      scope: 'source',
      sourceRef: preview.sourceRef,
      expectedRevision: preview.targetRevision,
      expectedSnapshotRevision: preview.snapshotRevision,
      requestId: 'source-delete',
    });
    const after = port.getSnapshot();
    for (const item of before.memories)
      expect(after.memories.find((row) => row.id === item.id)).toEqual(
        preview.affectedFactIds.includes(item.id)
          ? expect.objectContaining({ status: 'deleted', text: '', sourceRefs: [] })
          : item,
      );
    for (const item of before.profileItems)
      expect(after.profileItems.find((row) => row.id === item.id)).toEqual(
        preview.affectedProfileIds.includes(item.id) ? expect.objectContaining({ status: 'deleted', text: '' }) : item,
      );
    expect(after.proposals.find((item) => item.id === 'local-proposal-career')?.status).toBe('deleted');
    expect(after.proposals.find((item) => item.id === 'local-proposal')?.status).toBe('pending');
    expect(receipt.affectedIds).toEqual(
      expect.arrayContaining([
        ...preview.affectedFactIds,
        ...preview.affectedProfileIds,
        ...preview.affectedProposalIds,
      ]),
    );
    expect(port.readSource(before.memories[0].sourceRefs[0])).toMatchObject({ available: false, ref: { quote: '' } });
  });

  it('requires a fresh impact preview after another mutation rather than silently widening a confirmed delete', async () => {
    const port = createAboutMeStore(),
      preview = port.previewDelete('memory-basic', 'source');
    await port.execute({ type: 'profile-delete', id: 'profile-goals', expectedRevision: 1, requestId: 'other-change' });
    const current = port.getSnapshot();
    await expect(
      port.execute({
        type: 'memory-delete',
        id: preview.targetId,
        scope: preview.scope,
        sourceRef: preview.sourceRef,
        expectedRevision: preview.targetRevision,
        expectedSnapshotRevision: preview.snapshotRevision,
        requestId: 'stale-delete',
      }),
    ).rejects.toMatchObject({ status: 409 });
    expect(port.getSnapshot()).toBe(current);
    expect(current.memories[0].status).toBe('active');
  });

  it('requires an explicit source choice for a fact with multiple sources and deletes only the selected message', async () => {
    const seed = createAboutMeSeed();
    const basic = seed.memories[0],
      goal = seed.memories.find((item) => item.id === 'memory-goals')!;
    basic.sourceRefs.push(goal.sourceRefs[0]);
    const port = createAboutMeStore(seed);
    expect(() => port.previewDelete(basic.id, 'source')).toThrow('请选择');
    const preview = port.previewDelete(basic.id, 'source', goal.sourceRefs[0]);
    expect([...preview.affectedFactIds].sort()).toEqual(['memory-basic', 'memory-goals']);
    await port.execute({
      type: 'memory-delete',
      id: basic.id,
      scope: 'source',
      sourceRef: preview.sourceRef,
      expectedRevision: 1,
      expectedSnapshotRevision: 1,
      requestId: 'chosen-source',
    });
    const remainingLife = port.getSnapshot().memories.find((item) => item.id === 'memory-life')!;
    expect(remainingLife.status).toBe('active');
    expect(port.readSource(remainingLife.sourceRefs[0]).available).toBe(true);
  });

  it('does not cascade by matching summaries when the source message IDs differ', async () => {
    const seed = createAboutMeSeed();
    seed.memories.find((item) => item.id === 'memory-goals')!.text = seed.memories[0].text;
    const port = createAboutMeStore(seed),
      preview = port.previewDelete('memory-basic', 'source');
    expect(preview.affectedFactIds).not.toContain('memory-goals');
    await port.execute({
      type: 'memory-delete',
      id: preview.targetId,
      scope: 'source',
      sourceRef: preview.sourceRef,
      expectedRevision: 1,
      expectedSnapshotRevision: 1,
      requestId: 'message-not-summary',
    });
    expect(port.getSnapshot().memories.find((item) => item.id === 'memory-goals')?.status).toBe('active');
  });

  it('keeps an explicit user-edited profile after its former source is deleted', async () => {
    const port = createAboutMeStore();
    const edit = await port.execute({
      type: 'profile-edit',
      id: 'profile-basic',
      text: '请叫我小远。',
      expectedRevision: 1,
      requestId: 'user-priority',
    });
    const preview = port.previewDelete('memory-basic', 'source');
    expect(preview.affectedProfileIds).not.toContain('profile-basic');
    await port.execute({
      type: 'memory-delete',
      id: preview.targetId,
      scope: 'source',
      sourceRef: preview.sourceRef,
      expectedRevision: 1,
      expectedSnapshotRevision: 2,
      requestId: 'old-source-delete',
    });
    const item = port.getSnapshot().profileItems.find((row) => row.id === 'profile-basic')!;
    expect(item).toMatchObject({ text: '请叫我小远。', status: 'active', userEdited: true });
    expect(item.factIds).toEqual([edit.factId]);
    expect(port.readSource(item.sourceRefs[0]).available).toBe(true);
  });

  it('retains a higher-revision fact tombstone and rejects stale Chat operations without resurrection', async () => {
    const port = createNightPort(),
      preview = port.aboutMe.previewDelete('local-preference', 'fact');
    await port.aboutMe.execute({
      type: 'memory-delete',
      id: preview.targetId,
      scope: 'fact',
      expectedRevision: 1,
      expectedSnapshotRevision: 1,
      requestId: 'delete-fixed-id',
    });
    const old = {
      fact_id: 'local-preference',
      write_status: 'saved',
      summary: '偏好先看简短结论（合成示例）',
      revision: 1,
    };
    expect(port.memory.supports('undo', old)).toBe(false);
    await expect(port.memory.execute('undo', old)).rejects.toMatchObject({ status: 409 });
    await expect(
      port.aboutMe.execute({
        type: 'memory-edit',
        id: old.fact_id,
        text: '旧事件试图复活',
        expectedRevision: 1,
        requestId: 'stale-resurrect',
      }),
    ).rejects.toMatchObject({ status: 409 });
    expect(port.currentReceipts()).toContainEqual(
      expect.objectContaining({ fact_id: old.fact_id, revision: 2, write_status: 'deleted', summary: '' }),
    );
  });

  it('does not resurrect a deleted confirmed proposal when its old idempotent success is replayed', async () => {
    const port = createNightPort(),
      old = {
        proposal_id: 'local-proposal',
        write_status: 'pending_confirmation',
        summary: '希望跟进一项健康安排（合成示例）',
        category: 'health',
        revision: 1,
      };
    const confirmation = await port.memory.execute('remember', old);
    const preview = port.aboutMe.previewDelete(confirmation.fact_id!, 'source');
    await port.aboutMe.execute({
      type: 'memory-delete',
      id: preview.targetId,
      scope: 'source',
      sourceRef: preview.sourceRef,
      expectedRevision: preview.targetRevision,
      expectedSnapshotRevision: preview.snapshotRevision,
      requestId: 'delete-confirmed-source',
    });
    const before = port.aboutMe.getSnapshot();
    expect(await port.memory.execute('remember', old)).toBe(confirmation);
    expect(port.aboutMe.getSnapshot()).toBe(before);
    expect(port.currentReceipts().find((row) => row.fact_id === confirmation.fact_id)).toMatchObject({
      revision: 3,
      write_status: 'deleted',
      proposal_id: old.proposal_id,
    });
  });

  it('invalidates a dictionary association only when its precise source is deleted', async () => {
    const seed = createAboutMeSeed();
    seed.memories[0].sourceRefs = seed.dictionary[0].sourceRefs;
    const port = createAboutMeStore(seed),
      preview = port.previewDelete('memory-basic', 'source');
    expect(preview.affectedSymbolIds).toEqual(['symbol-star']);
    await port.execute({
      type: 'memory-delete',
      id: preview.targetId,
      scope: 'source',
      sourceRef: preview.sourceRef,
      expectedRevision: 1,
      expectedSnapshotRevision: 1,
      requestId: 'dictionary-source',
    });
    expect(port.getSnapshot().dictionary[0].status).toBe('deleted');
  });

  it('checks Unicode quote offsets as code points when a user correction contains emoji', async () => {
    const port = createAboutMeStore(),
      text = '请叫我小林🌿，喜欢简短回答。';
    await port.execute({
      type: 'profile-edit',
      id: 'profile-basic',
      text,
      expectedRevision: 1,
      requestId: 'unicode-edit',
    });
    const ref = port.getSnapshot().profileItems[0].sourceRefs[0];
    expect(ref.end).toBe(Array.from(text).length);
    expect(port.readSource(ref)).toMatchObject({ available: true, quote: text });
  });

  it('refuses raw birth fields in a custom seed while keeping safe chart summaries', () => {
    const seed = createAboutMeSeed();
    expect(
      createAboutMeStore(seed)
        .getSnapshot()
        .profileItems.find((item) => item.section === 'chart_summary')?.text,
    ).toContain('合成命理档案');
    seed.memories[0].text = 'birth.location.lng: 116.4';
    expect(() => createAboutMeStore(seed)).toThrow('出生原值');
  });
});
