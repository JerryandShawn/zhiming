import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { createOrganizeDemoPort, ORGANIZE_CONFIRMATION_TTL_MS } from '../src/organize/port';
import { createOrganizeSeed } from '../src/organize/seed';
import type { EditIntent, FieldKey, OrganizePort, OrganizeSeed } from '../src/organize/types';

const hash = async (text: string) => createHash('sha256').update(text).digest('hex');
let requestSequence = 0;
const request = () => `test-${++requestSequence}`;
function setup(seed: OrganizeSeed = createOrganizeSeed()) {
  let at = Date.parse('2026-10-21T01:00:00+08:00'),
    nonce = 0;
  return {
    port: createOrganizeDemoPort({ seed, now: () => at, digest: hash, nonce: () => `ticket-${++nonce}` }),
    advance: (ms: number) => {
      at += ms;
    },
  };
}
async function edit(port: OrganizePort, intent: EditIntent, request_id = request()) {
  return port.edit({ request_id, expected_revision: port.getSnapshot().revision, intent });
}
async function accept(port: OrganizePort, id = 'segment-2') {
  expect((await edit(port, { kind: 'accept', segment_id: id })).status).toBe('accepted');
}
async function apply(port: OrganizePort) {
  const ticket = port.prepareConfirmation({ action: 'apply' });
  return port.execute({ request_id: request(), ticket_id: ticket.id });
}
const originals = (port: OrganizePort) =>
  Object.values(port.getSnapshot().document.messages).map(
    ({ id, owner_id, subject_id, content, role, at_ms, revision, status }) => ({
      id,
      owner_id,
      subject_id,
      content,
      role,
      at_ms,
      revision,
      status,
    }),
  );

describe('organize v2 reviewed changes and offline command boundary', () => {
  it('starts with seven real wire spaces, eight pending segments and explicit synthetic degradation', () => {
    const { port } = setup(),
      snapshot = port.getSnapshot();
    expect(snapshot.spaces).toHaveLength(7);
    expect(snapshot.spaces.some((space) => space.id === 'metaphysics')).toBe(true);
    expect(snapshot.segments).toHaveLength(8);
    expect(snapshot.segments.filter((item) => item.needs_review)).toHaveLength(1);
    expect(snapshot.summary).toMatchObject({ pending_segments: 8, accepted_segments: 0, message_count: 0 });
    expect(snapshot.metadata).toMatchObject({
      mode: 'synthetic',
      module_sha: '8c554bd4af6788b3a4d98b9dd0d7618c591f7cfd',
    });
    expect(port.getSnapshot()).toBe(snapshot);
    expect(() => port.prepareConfirmation({ action: 'apply' })).toThrow('接受至少一个片段');
  });

  it('applies only accepted segments, preserves pending/rejected labels and every original message field', async () => {
    const { port } = setup(),
      before = originals(port),
      original = structuredClone(port.getSnapshot().document);
    await accept(port);
    await edit(port, { kind: 'reject', segment_id: 'segment-3' });
    expect(port.getSnapshot().document).toEqual(original);
    const ticket = port.prepareConfirmation({ action: 'apply' });
    expect(port.getSnapshot().document).toEqual(original);
    expect((await port.execute({ request_id: request(), ticket_id: ticket.id })).status).toBe('accepted');
    const snapshot = port.getSnapshot();
    expect(snapshot.document.messages['message-2'].topic_id).toBe('proposal-2');
    expect(snapshot.document.messages['message-3'].topic_id).toBe('legacy-all');
    expect(snapshot.document.messages['message-1'].topic_id).toBe('legacy-all');
    expect(snapshot.document.topics['legacy-all']).toEqual(original.topics['legacy-all']);
    expect(originals(port)).toEqual(before);
    expect(snapshot.applied?.fields.every((field) => field.label.startsWith('面试准备 · '))).toBe(true);
  });

  it('matches module wire keys and distinguishes absent from explicit null', async () => {
    const { port } = setup();
    await accept(port);
    const changes = port.getSnapshot().changeset!;
    expect(Object.keys(changes).sort()).toEqual([
      'batch_id',
      'inverse_ops',
      'ops',
      'owner_id',
      'source_guards',
      'subject_id',
    ]);
    const secondary = changes.ops.find((op) => op.field === 'space_secondary')!;
    expect(secondary.before).toEqual({ present: false });
    expect(secondary.after).toEqual({ present: true, value: null });
    expect(changes.inverse_ops).toEqual(
      [...changes.ops].reverse().map((op) => ({ ...op, before: op.after, after: op.before })),
    );
    expect(changes.source_guards.map((guard) => [guard.collection, guard.entity_id])).toEqual([
      ['messages', 'message-2'],
      ['topics', 'legacy-all'],
    ]);
    expect(changes.source_guards.every((guard) => /^[a-f0-9]{64}$/.test(guard.immutable_digest))).toBe(true);
  });

  it('moves, renames and merges reviewed drafts without deleting original topics or messages', async () => {
    const { port } = setup(),
      before = originals(port);
    await edit(port, { kind: 'rename_topic', topic_id: 'proposal-2', title: '新的面试笔记' });
    await edit(port, { kind: 'move_segment', segment_id: 'segment-3', target_topic_id: 'proposal-2' });
    await edit(port, { kind: 'move_topic', topic_id: 'proposal-2', space_id: 'family' });
    await accept(port);
    await accept(port, 'segment-3');
    await apply(port);
    expect(port.getSnapshot().document.topics['proposal-2']).toMatchObject({
      title: '新的面试笔记',
      space_id: 'family',
      message_ids: ['message-2', 'message-3'],
    });
    expect(port.getSnapshot().document.topics['legacy-all']).toBeDefined();
    expect(originals(port)).toEqual(before);
    const second = setup().port;
    expect(
      (await edit(second, { kind: 'merge_topics', topic_ids: ['proposal-2'], target_topic_id: 'proposal-3' })).status,
    ).toBe('accepted');
    expect(second.getSnapshot().segments.find((item) => item.id === 'segment-2')?.topic_id).toBe('proposal-3');
    expect(
      (await edit(second, { kind: 'merge_topics', topic_ids: ['proposal-3'], target_topic_id: 'proposal-5' })).status,
    ).toBe('rejected');
  });

  it('keeps both snapshot and original data unchanged on invalid edits or stale revision', async () => {
    const { port } = setup(),
      before = port.getSnapshot();
    expect((await edit(port, { kind: 'rename_topic', topic_id: 'proposal-2', title: ' ' })).status).toBe('rejected');
    expect(port.getSnapshot()).toBe(before);
    expect(
      (
        await port.edit({
          request_id: request(),
          expected_revision: 0,
          intent: { kind: 'accept', segment_id: 'segment-2' },
        })
      ).code,
    ).toBe('CONFLICT');
    expect(port.getSnapshot()).toBe(before);
    expect((await edit(port, { kind: 'rename_topic', topic_id: 'proposal-2', title: '🌿'.repeat(80) })).status).toBe(
      'accepted',
    );
    expect((await edit(port, { kind: 'rename_topic', topic_id: 'proposal-2', title: '🌿'.repeat(81) })).status).toBe(
      'rejected',
    );
  });

  it('makes command and valid ticket preparation replay stable, and rejects changed payload under the same request ID', async () => {
    const { port } = setup(),
      revision = port.getSnapshot().revision,
      request_id = request();
    const command = {
      request_id,
      expected_revision: revision,
      intent: { kind: 'accept' as const, segment_id: 'segment-2' },
    };
    const receipt = await port.edit(command),
      snapshot = port.getSnapshot();
    expect(await port.edit(command)).toBe(receipt);
    expect(port.getSnapshot()).toBe(snapshot);
    expect((await port.edit({ ...command, intent: { kind: 'reject', segment_id: 'segment-2' } })).code).toBe(
      'REPLAY_CHANGED',
    );
    const ticket = port.prepareConfirmation({ action: 'apply' });
    expect(port.prepareConfirmation({ action: 'apply' })).toBe(ticket);
    const applyCommand = { request_id: request(), ticket_id: ticket.id };
    const applied = await port.execute(applyCommand),
      after = port.getSnapshot();
    expect(await port.execute(applyCommand)).toBe(applied);
    expect(port.getSnapshot()).toBe(after);
    expect((await port.execute({ request_id: request(), ticket_id: ticket.id })).code).toBe('CONSUMED');
  });

  it.each([ORGANIZE_CONFIRMATION_TTL_MS, ORGANIZE_CONFIRMATION_TTL_MS + 1, -1])(
    'rejects expired or backwards-clock apply confirmation at offset %i',
    async (offset) => {
      const { port, advance } = setup();
      await accept(port);
      const ticket = port.prepareConfirmation({ action: 'apply' }),
        before = port.getSnapshot();
      advance(offset);
      const result = await port.execute({ request_id: request(), ticket_id: ticket.id });
      expect(result).toMatchObject({ status: 'rejected', code: 'EXPIRED', message: '这张卡已过期，我重新发一张' });
      expect(port.getSnapshot()).toBe(before);
      if (offset > 0) expect(port.prepareConfirmation({ action: 'apply' }).id).not.toBe(ticket.id);
    },
  );

  it('accepts just before expiry and invalidates confirmation after any new draft revision', async () => {
    const first = setup();
    await accept(first.port);
    const ticket = first.port.prepareConfirmation({ action: 'apply' });
    first.advance(ORGANIZE_CONFIRMATION_TTL_MS - 1);
    expect((await first.port.execute({ request_id: request(), ticket_id: ticket.id })).status).toBe('accepted');
    const second = setup();
    await accept(second.port);
    const old = second.port.prepareConfirmation({ action: 'apply' });
    await edit(second.port, { kind: 'rename_topic', topic_id: 'proposal-2', title: '重新核对过的标题' });
    expect((await second.port.execute({ request_id: request(), ticket_id: old.id })).code).toBe('CONFLICT');
    expect(second.port.getSnapshot().status).toBe('draft');
  });

  it('requires separate confirmation for revert and never resurrects a reverted batch', async () => {
    const { port, advance } = setup(),
      before = structuredClone(port.getSnapshot().document);
    await accept(port);
    await apply(port);
    const ticket = port.prepareConfirmation({ action: 'revert' });
    advance(ORGANIZE_CONFIRMATION_TTL_MS);
    expect((await port.execute({ request_id: request(), ticket_id: ticket.id })).code).toBe('EXPIRED');
    expect(port.getSnapshot().status).toBe('applied');
    const current = port.prepareConfirmation({ action: 'revert' });
    expect((await port.execute({ request_id: request(), ticket_id: current.id })).status).toBe('accepted');
    expect(port.getSnapshot().document).toEqual(before);
    expect(port.getSnapshot().status).toBe('reverted');
    expect(() => port.prepareConfirmation({ action: 'apply' })).toThrow();
  });

  it('rejects an inconsistent field subset atomically, but supports routing group then created-topic undo', async () => {
    const { port } = setup();
    await accept(port);
    await apply(port);
    const before = port.getSnapshot(),
      field = before.applied!.fields.find((item) => item.field === 'space_id')!;
    const invalid = port.prepareConfirmation({ action: 'revert', fields: [field] });
    expect((await port.execute({ request_id: request(), ticket_id: invalid.id })).code).toBe('INVALID_SELECTION');
    expect(port.getSnapshot()).toBe(before);
    const group = before.applied!.fields.filter((item) => item.collection === 'messages');
    const routing = port.prepareConfirmation({ action: 'revert', fields: group });
    expect((await port.execute({ request_id: request(), ticket_id: routing.id })).status).toBe('accepted');
    expect(port.getSnapshot().status).toBe('partially_reverted');
    expect(port.getSnapshot().document.messages['message-2'].topic_id).toBe('legacy-all');
    expect(port.getSnapshot().document.topics['proposal-2']).toBeDefined();
    const final = port.prepareConfirmation({ action: 'revert' });
    await port.execute({ request_id: request(), ticket_id: final.id });
    expect(port.getSnapshot().status).toBe('reverted');
    expect(port.getSnapshot().document.topics['proposal-2']).toBeUndefined();
  });

  it('preserves a later-edited field and reports partial undo without exposing values in conflicts', async () => {
    const { port } = setup();
    await accept(port);
    await apply(port);
    const next = structuredClone(port.getSnapshot().document);
    next.topics['proposal-2'].title = '用户后来写的新标题';
    port.refresh(next);
    const ticket = port.prepareConfirmation({ action: 'revert' });
    expect((await port.execute({ request_id: request(), ticket_id: ticket.id })).status).toBe('accepted');
    expect(port.getSnapshot().document.topics['proposal-2'].title).toBe('用户后来写的新标题');
    expect(port.getSnapshot().document.messages['message-2'].topic_id).toBe('legacy-all');
    expect(port.getSnapshot().status).toBe('partially_reverted');
    expect(port.getSnapshot().conflicts[0]).toMatchObject({
      collection: 'topics',
      field: null,
      reason: 'field_changed',
    });
    expect(JSON.stringify(port.getSnapshot().conflicts)).not.toContain('用户后来写的新标题');
  });

  it('keeps a newly created topic when later messages still reference it', async () => {
    const { port } = setup();
    await accept(port);
    await apply(port);
    const next = structuredClone(port.getSnapshot().document);
    next.messages.later = { ...next.messages['message-2'], id: 'later', content: '后来新增的合成消息' };
    port.refresh(next);
    const ticket = port.prepareConfirmation({ action: 'revert' });
    await port.execute({ request_id: request(), ticket_id: ticket.id });
    expect(port.getSnapshot().document.topics['proposal-2']).toBeDefined();
    expect(port.getSnapshot().document.messages.later.topic_id).toBe('proposal-2');
    expect(port.getSnapshot().conflicts[0].reason).toBe('later_references');
  });

  it('keeps unrelated concurrent labels and rejects apply when a before-field changed', async () => {
    const { port } = setup();
    await accept(port);
    const next = structuredClone(port.getSnapshot().document);
    next.messages['message-2'].route_confidence = 0.25;
    port.refresh(next);
    const before = port.getSnapshot();
    expect((await apply(port)).code).toBe('CONFLICT');
    expect(port.getSnapshot()).toBe(before);
    expect(port.getSnapshot().document.topics['proposal-2']).toBeUndefined();
  });

  it('rejects cross-owner refresh without changing snapshot or confirmation', async () => {
    const { port } = setup(),
      snapshot = port.getSnapshot(),
      next = structuredClone(snapshot.document);
    next.owner_id = 'another-owner';
    expect(() => port.refresh(next)).toThrow('归属不匹配');
    expect(port.getSnapshot()).toBe(snapshot);
  });

  it.each(['revoked', 'withdrawn', 'deleted', 'content', 'revision', 'incognito', 'thread', 'retention', 'topic'])(
    'rechecks %s source lifecycle at apply, not just at suggestion generation',
    async (mode) => {
      const { port } = setup();
      await accept(port);
      const next = structuredClone(port.getSnapshot().document),
        row = next.messages['message-2'];
      if (['revoked', 'withdrawn', 'deleted'].includes(mode)) row.status = mode;
      if (mode === 'content') row.content = '已更正的合成原文';
      if (mode === 'revision') row.revision++;
      if (mode === 'incognito') row.incognito = true;
      if (mode === 'thread') row.thread_id = 'incognito:temporary';
      if (mode === 'retention') row.retention_scope = 'temporary';
      if (mode === 'topic') next.topics['legacy-all'].status = 'revoked';
      port.refresh(next);
      const before = port.getSnapshot();
      expect((await apply(port)).code).toBe('SOURCE_CHANGED');
      expect(port.getSnapshot()).toBe(before);
    },
  );

  it('also rejects source withdrawal when undoing an already-applied batch', async () => {
    const { port } = setup();
    await accept(port);
    await apply(port);
    const next = structuredClone(port.getSnapshot().document);
    next.messages['message-2'].status = 'withdrawn';
    port.refresh(next);
    const before = port.getSnapshot(),
      ticket = port.prepareConfirmation({ action: 'revert' });
    expect((await port.execute({ request_id: request(), ticket_id: ticket.id })).code).toBe('SOURCE_CHANGED');
    expect(port.getSnapshot()).toBe(before);
  });

  it('binds selected fields and freezes ticket scope against caller mutation', async () => {
    const { port } = setup();
    await accept(port);
    await apply(port);
    const field: FieldKey = { collection: 'messages', entity_id: 'message-2', field: 'route_confidence' };
    const ticket = port.prepareConfirmation({ action: 'revert', fields: [field] });
    field.field = 'topic_id';
    expect(ticket.fields?.[0].field).toBe('route_confidence');
    expect(() => {
      ticket.fields![0].field = 'topic_id';
    }).toThrow();
    const unknown: FieldKey = { collection: 'messages', entity_id: 'missing', field: 'topic_id' };
    expect(() => port.prepareConfirmation({ action: 'revert', fields: [unknown] })).toThrow();
  });

  it('does not let a throwing view observer roll back a confirmed local apply', async () => {
    const { port } = setup();
    await accept(port);
    port.subscribe(() => {
      throw new Error('view unmounted');
    });
    expect((await apply(port)).status).toBe('accepted');
    expect(port.getSnapshot().status).toBe('applied');
  });
});
