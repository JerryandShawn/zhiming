import { describe, expect, it, vi } from 'vitest';
import { DraftApiError } from '../src/modules/draftApi';
import { clearDraftRetry, draftRetryIntent } from '../src/modules/draftRetry';

describe('draft write retry identity', () => {
  it('retains the exact request identity across a fresh intent and clears it only after confirmation', () => {
    const scope = 'test:persistent';
    const first = draftRetryIntent(scope, 2, { title: '原内容' });
    const retried = draftRetryIntent(scope, 2, { title: '原内容' });
    expect(retried).toEqual(first);
    expect(() => draftRetryIntent(scope, 2, { title: '改动内容' })).toThrowError(DraftApiError);
    clearDraftRetry(scope, 'web:not-the-pending-request');
    expect(draftRetryIntent(scope, 2, { title: '原内容' })).toEqual(first);
    clearDraftRetry(scope, first.request_id);
    const next = draftRetryIntent(scope, 2, { title: '改动内容' });
    expect(next.request_id).not.toBe(first.request_id);
    clearDraftRetry(scope, next.request_id);
  });

  it('keeps volatile preview retries out of browser storage', () => {
    const writes = vi.spyOn(Storage.prototype, 'setItem');
    const scope = 'test:volatile';
    const first = draftRetryIntent(scope, 0, { title: '合成内容' }, false);
    expect(draftRetryIntent(scope, 0, { title: '合成内容' }, false)).toEqual(first);
    expect(writes).not.toHaveBeenCalled();
    clearDraftRetry(scope, first.request_id, false);
  });

  it('does not send a durable write when its retry identity cannot be stored', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    expect(() => draftRetryIntent('test:unavailable-storage', 0, { title: '不能发送' })).toThrowError(
      '还没有确认是否已保存',
    );
  });
});
