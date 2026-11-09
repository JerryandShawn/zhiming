import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { createOrganizeDemoPort } from '../src/organize/port';
import { createOrganizeSeed } from '../src/organize/seed';
import { STOPPED_SOURCE_MESSAGE } from '../src/organize/sourceProjection';

const digest = async (text: string) => createHash('sha256').update(text).digest('hex');
const setup = () => {
  let nonce = 0;
  return createOrganizeDemoPort({
    now: () => Date.parse('2026-10-21T01:00:00+08:00'),
    digest,
    nonce: () => `source-ticket-${++nonce}`,
  });
};

describe('organize source display projection and late callbacks', () => {
  it.each(['withdrawn', 'incognito', 'revision', 'topic'])(
    'conceals stopped %s sources without mutating the immutable ledger',
    async (mode) => {
      const port = setup();
      await port.edit({
        request_id: 'accept',
        expected_revision: 1,
        intent: { kind: 'accept', segment_id: 'segment-2' },
      });
      const guard = structuredClone(port.getSnapshot().changeset!.source_guards);
      const next = structuredClone(port.getSnapshot().document),
        text = next.messages['message-2'].content;
      if (mode === 'withdrawn') next.messages['message-2'].status = 'withdrawn';
      if (mode === 'incognito') next.messages['message-2'].incognito = true;
      if (mode === 'revision') next.messages['message-2'].revision++;
      if (mode === 'topic') next.topics['legacy-all'].status = 'revoked';
      port.refresh(next);
      const snapshot = port.getSnapshot(),
        segment = snapshot.segments.find((item) => item.id === 'segment-2')!;
      expect(segment).toMatchObject({ source_available: false, sample: STOPPED_SOURCE_MESSAGE });
      expect(snapshot.document.messages['message-2'].content).toBe('');
      expect(JSON.stringify(snapshot)).not.toContain(text);
      expect(snapshot.changeset!.source_guards).toEqual(guard);
      const ticket = port.prepareConfirmation({ action: 'apply' });
      expect((await port.execute({ request_id: 'apply', ticket_id: ticket.id })).code).toBe('SOURCE_CHANGED');
      expect(port.getSnapshot()).toBe(snapshot);
      expect(next.messages['message-2'].content).toBe(text);
    },
  );

  it('retains active source text and hides every message in a partly invalidated fragment', () => {
    const seed = createOrganizeSeed();
    const first = seed.segments[0],
      second = seed.segments[1];
    first.message_ids.push(...second.message_ids);
    first.end = second.end;
    seed.segments.splice(1, 1);
    seed.topics[0].message_ids.push(...second.message_ids);
    seed.topics.splice(1, 1);
    const port = createOrganizeDemoPort({ seed, digest });
    const next = structuredClone(port.getSnapshot().document);
    const active = next.messages['message-3'].content;
    next.messages['message-2'].status = 'revoked';
    port.refresh(next);
    expect(port.getSnapshot().document.messages['message-1'].content).toBe('');
    expect(port.getSnapshot().document.messages['message-2'].content).toBe('');
    expect(port.getSnapshot().document.messages['message-3'].content).toBe(active);
  });

  it('does not commit an async draft result after an external source refresh', async () => {
    let release: (() => void)[] = [];
    let blocked = true;
    const port = createOrganizeDemoPort({
      digest: (text) =>
        blocked
          ? new Promise<string>((resolve) => {
              release.push(() => {
                void digest(text).then(resolve);
              });
            })
          : digest(text),
    });
    const pending = port.edit({
      request_id: 'late',
      expected_revision: 1,
      intent: { kind: 'accept', segment_id: 'segment-2' },
    });
    await Promise.resolve();
    const next = structuredClone(port.getSnapshot().document);
    next.messages['message-2'].revision++;
    port.refresh(next);
    const snapshot = port.getSnapshot();
    blocked = false;
    release.forEach((done) => done());
    release = [];
    expect((await pending).code).toBe('CONFLICT');
    expect(port.getSnapshot()).toBe(snapshot);
    expect(port.getSnapshot().segments.find((item) => item.id === 'segment-2')!.decision).toBe('pending');
  });

  it('rechecks ticket version and deadline after async source proof validation', async () => {
    let blocked = false,
      release: (() => void) | undefined,
      at = Date.parse('2026-10-21T01:00:00+08:00');
    const port = createOrganizeDemoPort({
      now: () => at,
      nonce: () => 'async-ticket',
      digest: (text) =>
        blocked
          ? new Promise<string>((resolve) => {
              release = () => {
                void digest(text).then(resolve);
              };
            })
          : digest(text),
    });
    await port.edit({
      request_id: 'accept',
      expected_revision: 1,
      intent: { kind: 'accept', segment_id: 'segment-2' },
    });
    const ticket = port.prepareConfirmation({ action: 'apply' }),
      before = port.getSnapshot();
    blocked = true;
    const pending = port.execute({ request_id: 'apply', ticket_id: ticket.id });
    await Promise.resolve();
    at = ticket.expires_at_ms;
    blocked = false;
    release!();
    expect((await pending).code).toBe('EXPIRED');
    expect(port.getSnapshot()).toBe(before);
    expect(port.getSnapshot().status).toBe('draft');
  });
});
