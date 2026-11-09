import { describe, expect, it } from 'vitest';
import { scheduleReceipt } from '../src/live/ReportSchedule';
import type { Schedule } from '../src/live/types';

describe('report receipt confirms the submitted policy', () => {
  const row: Schedule = {
    kind: 'daily',
    revision: 4,
    enabled: true,
    time: '07:00',
    status: 'active',
    configured: true,
    can_modify: true,
    receipt: { id: 'daily', kind: 'report_schedule', revision: 4, write_status: 'saved' },
  };
  it('accepts a matching confirmed policy and rejects another saved policy', () => {
    expect(scheduleReceipt(row, 'daily', { enabled: true, time: '07:00' })).toBe(true);
    expect(scheduleReceipt(row, 'daily', { enabled: true, time: '08:00' })).toBe(false);
    expect(scheduleReceipt(row, 'daily', { enabled: false, time: '07:00' })).toBe(false);
  });
  it('rejects a receipt for a different revision', () => {
    expect(
      scheduleReceipt({ ...row, receipt: { ...row.receipt!, revision: 3 } }, 'daily', { enabled: true, time: '07:00' }),
    ).toBe(false);
  });
});
