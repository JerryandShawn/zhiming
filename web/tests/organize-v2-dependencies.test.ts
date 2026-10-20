import { createHash } from 'node:crypto';
import { expect, it } from 'vitest';
import { createOrganizeDemoPort } from '../src/organize/port';

it('rejects an isolated created-topic undo before consuming any field, then permits a complete undo', async () => {
  const port = createOrganizeDemoPort({
    digest: async (text) => createHash('sha256').update(text).digest('hex'),
    now: () => Date.parse('2026-10-21T01:00:00+08:00'),
  });
  const original = structuredClone(port.getSnapshot().document);
  await port.edit({ request_id: 'accept', expected_revision: 1, intent: { kind: 'accept', segment_id: 'segment-2' } });
  const apply = port.prepareConfirmation({ action: 'apply' });
  await port.execute({ request_id: 'apply', ticket_id: apply.id });
  const applied = port.getSnapshot();
  const topic = applied.applied!.fields.find((field) => field.collection === 'topics' && field.field === null)!;
  expect(() => port.prepareConfirmation({ action: 'revert', fields: [topic] })).toThrow('归属标签');
  expect(port.getSnapshot()).toBe(applied);
  expect(port.getSnapshot().applied!.fields.every((field) => field.state === 'applied')).toBe(true);
  const undo = port.prepareConfirmation({ action: 'revert' });
  expect((await port.execute({ request_id: 'undo', ticket_id: undo.id })).status).toBe('accepted');
  expect(port.getSnapshot().status).toBe('reverted');
  expect(port.getSnapshot().document).toEqual(original);
});

it('binds only structured field keys in a confirmation scope, without duplicating before/after values', async () => {
  const port = createOrganizeDemoPort({ digest: async (text) => createHash('sha256').update(text).digest('hex') });
  await port.edit({ request_id: 'accept', expected_revision: 1, intent: { kind: 'accept', segment_id: 'segment-2' } });
  const apply = port.prepareConfirmation({ action: 'apply' });
  await port.execute({ request_id: 'apply', ticket_id: apply.id });
  const field = port.getSnapshot().applied!.fields.find((item) => item.field === 'route_confidence')!;
  const ticket = port.prepareConfirmation({ action: 'revert', fields: [field] });
  expect(Object.keys(ticket.fields![0]).sort()).toEqual(['collection', 'entity_id', 'field']);
});
