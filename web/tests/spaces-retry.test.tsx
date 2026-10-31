import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LiveSpaces from '../src/spaces/LiveSpaces';
import { createSpacesFakeFetch } from '../src/spaces/fakeServer';

describe('spaces draft retries', () => {
  it('resends the identical create request after an ambiguous network failure', async () => {
    window.location.hash = '#/spaces?space=career';
    const fake = createSpacesFakeFetch();
    const bodies: string[] = [];
    let fail = true;
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') {
        bodies.push(String(init.body));
        if (fail) {
          fail = false;
          throw new TypeError('offline');
        }
      }
      return fake(input, init);
    });
    const writes = vi.spyOn(Storage.prototype, 'setItem');
    render(<LiveSpaces preview suppliedFetcher={fetcher} />);
    expect(await screen.findByRole('heading', { name: '合成样例：是否换岗' })).toBeVisible();
    await userEvent.type(screen.getByRole('textbox', { name: '新话题名称' }), '合成重试话题');
    await userEvent.click(screen.getByRole('button', { name: /^新建话题$/ }));
    expect(await screen.findByText(/网络没有连上/)).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: /^新建话题$/ }));
    expect(await screen.findByText('新建话题已保存。')).toBeVisible();
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toBe(bodies[0]);
    expect(writes).not.toHaveBeenCalled();
  });
});
