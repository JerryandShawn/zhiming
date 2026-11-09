import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvidenceSource } from '../src/tools/EvidenceButton';
import WindowSearchPage, { windowChoiceLabel } from '../src/tools/WindowSearchPage';
import { createToolDemoPort } from '../src/tools/port';
import { publicEvidence, windowFixture } from './tools-test-fixtures';
import type { PublicEvidence, WindowChoice } from '../src/tools/types';

describe('public method/source labels', () => {
  it('shows the actual controlled school, source and limits with a safe official link', () => {
    const item: PublicEvidence = {
      ...publicEvidence(`tool-${'a'.repeat(64)}`, 'r1'),
      kind: 'rule',
      school: 'installed-constant',
      school_label: '热带地心五大相位（统一容许度）',
      source: {
        title: 'Swiss Ephemeris 官方接口',
        url: 'https://www.astro.com/swisseph/swephprg.htm',
        status: '数值历表接口；不证明关系效度',
      },
    };
    render(<EvidenceSource item={item} />);
    expect(screen.getByText(/热带地心五大相位/)).toBeVisible();
    expect(screen.getByText(/不证明关系效度/)).toBeVisible();
    const link = screen.getByRole('link', { name: 'Swiss Ephemeris 官方接口' });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('does not turn arbitrary URLs into clickable sources or invent missing metadata', () => {
    const base = { ...publicEvidence(`tool-${'a'.repeat(64)}`, 'r1'), kind: 'rule' as const };
    const mounted = render(
      <EvidenceSource
        item={{
          ...base,
          school_label: '项目方法',
          source: { title: '未登记链接', url: 'https://untrusted.invalid/source' },
        }}
      />,
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    mounted.rerender(<EvidenceSource item={base} />);
    expect(screen.getByText(/流派与出处尚未接入/)).toBeVisible();
    expect(screen.queryByText('项目方法')).not.toBeInTheDocument();
  });
});

const choice = (total: number, returned: number, first: number | null, last: number | null): WindowChoice => ({
  purpose: '签约',
  startDate: '2026-10-21',
  endDate: '2026-10-27',
  offset: 100,
  limit: 31,
  summary: { total, returned, first_rank: first, last_rank: last },
});
describe('human readable range choices', () => {
  it('uses real counts/ranks rather than hard coded seven-day offsets', () => {
    expect(windowChoiceLabel(choice(12, 12, 1, 12))).toBe('全部 12 天');
    expect(windowChoiceLabel(choice(12, 3, 4, 6))).toBe('第 4–6 名');
    expect(windowChoiceLabel(choice(12, 1, 12, 12))).toBe('第 12 名');
    expect(windowChoiceLabel(choice(12, 0, null, null))).toBe('末尾空页');
  });

  it('keeps offset/limit out of the primary selector and supports keyboard opening', () => {
    const port = createToolDemoPort([windowFixture()]);
    render(<WindowSearchPage port={port} />);
    const select = screen.getByRole('combobox', { name: '查看范围' });
    expect(select).toHaveTextContent('全部 1 天');
    expect(select).not.toHaveTextContent(/偏移|上限/);
    fireEvent.keyDown(select, { key: 'ArrowDown' });
    expect(screen.getByRole('option', { name: '全部 1 天' })).toBeVisible();
  });
});
