import { createHash } from 'node:crypto';
import { expect, it } from 'vitest';
import { createOrganizeDemoPort } from '../src/organize/port';

it('preserves a later same-space topic reroute as an atomic label group while undoing safe neighbour groups', async () => {
  let nonce = 0;
  const port = createOrganizeDemoPort({
    digest: async (text) => createHash('sha256').update(text).digest('hex'),
    now: () => Date.parse('2026-10-21T01:00:00+08:00'),
    nonce: () => `cas-${++nonce}`,
  });
  for (const id of ['segment-2', 'segment-3'])
    await port.edit({
      request_id: id,
      expected_revision: port.getSnapshot().revision,
      intent: { kind: 'accept', segment_id: id },
    });
  const apply = port.prepareConfirmation({ action: 'apply' });
  expect((await port.execute({ request_id: 'apply', ticket_id: apply.id })).status).toBe('accepted');
  const current = structuredClone(port.getSnapshot().document);
  current.messages['message-2'].topic_id = 'proposal-3';
  port.refresh(current);
  const revert = port.prepareConfirmation({ action: 'revert' });
  const receipt = await port.execute({ request_id: 'revert', ticket_id: revert.id });
  expect(receipt.status).toBe('accepted');
  const snapshot = port.getSnapshot();
  expect(snapshot.status).toBe('partially_reverted');
  expect(snapshot.document.messages['message-2']).toMatchObject({ topic_id: 'proposal-3', space_id: 'career' });
  expect(snapshot.document.messages['message-3']).toMatchObject({ topic_id: 'legacy-all', space_id: 'daily' });
  expect(snapshot.document.topics['proposal-3']).toBeDefined();
  expect(snapshot.document.topics['proposal-2']).toBeUndefined();
  expect(snapshot.conflicts.some((item) => item.collection === 'messages' && item.entity_id === 'message-2')).toBe(
    true,
  );
  expect(snapshot.conflicts.some((item) => item.entity_id === 'proposal-3' && item.reason === 'later_references')).toBe(
    true,
  );
  expect(
    snapshot
      .applied!.fields.filter((item) => item.entity_id === 'message-2')
      .every((item) => item.state === 'conflict'),
  ).toBe(true);
  expect(
    snapshot
      .applied!.fields.filter((item) => item.entity_id === 'message-3')
      .every((item) => item.state === 'reverted'),
  ).toBe(true);
});
