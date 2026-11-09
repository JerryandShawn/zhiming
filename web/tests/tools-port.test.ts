import { describe, expect, it } from 'vitest';
import { createToolDemoPort, synastryKey } from '../src/tools/port';
import { freshConsent, gate, synastryFixture, synastryQuery, windowFixture } from './tools-test-fixtures';

describe('tool viewer evidence activation', () => {
  it('exposes no evidence before a successful read and revokes it on reset', async () => {
    const sample = windowFixture(),
      port = createToolDemoPort([sample]);
    const reference = sample.evidence[0].ref;
    expect(port.resolveEvidence(reference)).toBeUndefined();
    await port.windowSearch(port.windows[0]);
    expect(port.resolveEvidence(reference)?.summary).toBe('独立合成依据');
    port.reset();
    expect(port.resolveEvidence(reference)).toBeUndefined();
  });

  it('keeps repeated short aliases and page documents separate', async () => {
    const first = windowFixture('a'),
      second = windowFixture('b', 1);
    const port = createToolDemoPort([first, second]);
    await port.windowSearch(port.windows[0]);
    expect(port.resolveEvidence(second.evidence[0].ref)).toBeUndefined();
    await port.windowSearch(port.windows[1]);
    expect(port.resolveEvidence(first.evidence[0].ref)).toBeUndefined();
    expect(port.resolveEvidence(second.evidence[0].ref)).toBeDefined();
  });

  it('gives sibling viewers independent grants even for the same document', async () => {
    const sample = synastryFixture(),
      root = createToolDemoPort([sample]);
    const left = root.createScope(),
      right = root.createScope(),
      reference = sample.evidence[0].ref;
    await left.synastry(synastryQuery, freshConsent());
    expect(root.resolveEvidence(reference)).toBeUndefined();
    expect(right.resolveEvidence(reference)).toBeUndefined();
    await right.synastry(synastryQuery, freshConsent());
    left.reset();
    expect(left.resolveEvidence(reference)).toBeUndefined();
    expect(right.resolveEvidence(reference)).toBeDefined();
  });

  it('requires both exact fresh confirmations and never trusts sample consent', async () => {
    const sample = synastryFixture(),
      port = createToolDemoPort([sample]);
    await expect(port.synastry(synastryQuery, undefined)).rejects.toMatchObject({ code: 'CONSENT_REQUIRED' });
    await expect(port.synastry(synastryQuery, { ...freshConsent(), b: false } as never)).rejects.toMatchObject({
      code: 'CONSENT_REQUIRED',
    });
    const changed = { ...synastryQuery, kind: 'friendship' as const };
    await expect(port.synastry(changed, freshConsent())).rejects.toMatchObject({ code: 'CONSENT_REQUIRED' });
    expect(port.resolveEvidence(sample.evidence[0].ref)).toBeUndefined();
    expect(synastryKey(changed)).not.toBe(synastryKey(synastryQuery));
  });

  it('does not let a reset or aborted request reactivate its old document', async () => {
    const waiting = gate<void>(),
      sample = synastryFixture();
    const port = createToolDemoPort([sample], () => waiting.promise);
    const pending = port.synastry(synastryQuery, freshConsent());
    const rejected = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    port.reset();
    waiting.resolve();
    await rejected;
    expect(port.resolveEvidence(sample.evidence[0].ref)).toBeUndefined();
    const controller = new AbortController();
    controller.abort();
    await expect(port.synastry(synastryQuery, freshConsent(), controller.signal)).rejects.toMatchObject({
      name: 'AbortError',
    });
  });

  it('clears activation before an unavailable or invalid new request', async () => {
    const sample = windowFixture(),
      port = createToolDemoPort([sample]);
    await port.windowSearch(port.windows[0]);
    expect(await port.windowSearch({ ...port.windows[0], purpose: '出行' })).toMatchObject({ status: 'unavailable' });
    expect(port.resolveEvidence(sample.evidence[0].ref)).toBeUndefined();
    await port.windowSearch(port.windows[0]);
    await expect(port.windowSearch({ ...port.windows[0], startDate: '2026-02-30' })).rejects.toMatchObject({
      code: 'INVALID_INPUT',
    });
    expect(port.resolveEvidence(sample.evidence[0].ref)).toBeUndefined();
  });

  it('a newer read keeps its document when an older read finishes last', async () => {
    const first = windowFixture('a'),
      second = windowFixture('b', 1);
    const gates = [gate<void>(), gate<void>()];
    let index = 0;
    const port = createToolDemoPort([first, second], () => gates[index++].promise);
    const oldRead = port.windowSearch(port.windows[0]);
    const rejected = expect(oldRead).rejects.toMatchObject({ name: 'AbortError' });
    const newRead = port.windowSearch(port.windows[1]);
    gates[1].resolve();
    await newRead;
    gates[0].resolve();
    await rejected;
    expect(port.resolveEvidence(first.evidence[0].ref)).toBeUndefined();
    expect(port.resolveEvidence(second.evidence[0].ref)).toBeDefined();
  });

  it('freezes input ownership and returns copies of active evidence', async () => {
    const sample = windowFixture(),
      port = createToolDemoPort([sample]);
    sample.evidence[0].summary = '外部后来修改';
    await port.windowSearch(port.windows[0]);
    const first = port.resolveEvidence(sample.evidence[0].ref)!;
    first.summary = '消费者后来修改';
    expect(port.resolveEvidence(sample.evidence[0].ref)?.summary).toBe('独立合成依据');
  });

  it('rejects duplicated documents, aliases and cross-document linked evidence', () => {
    const sample = windowFixture();
    expect(() => createToolDemoPort([sample, structuredClone(sample)])).toThrow('当前条件或公开样例暂不可用');
    const repeated = structuredClone(sample);
    repeated.evidence.push(structuredClone(repeated.evidence[0]));
    expect(() => createToolDemoPort([repeated])).toThrow();
    const linked = structuredClone(sample);
    linked.evidence[0].evidence_refs = [{ ...linked.evidence[0].ref, document_id: synastryFixture().document_id }];
    expect(() => createToolDemoPort([linked])).toThrow();
  });
});
