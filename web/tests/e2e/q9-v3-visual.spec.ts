import { test as base, expect, type APIRequestContext } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import {
  backend,
  captureV3,
  fixedDate,
  fixtureSafety,
  guardV3,
  names,
  openPopulatedV3,
  writeEvidence,
  type Seed,
} from './q9-v3-helpers';

async function seedOwner(api: APIRequestContext): Promise<Seed> {
  await fixtureSafety(api);
  const created = await api.post('/__test__/owner');
  expect(created.ok(), 'Create an isolated synthetic fixture owner').toBe(true);
  const { token } = (await created.json()) as { token: string };
  expect(typeof token).toBe('string');
  const headers = { 'X-Token': token };
  const state = await api.get('/api/state', { headers });
  expect(state.ok()).toBe(true);
  const { revision } = (await state.json()) as { revision: number };
  const confirmed = await api.post('/api/subjects/self/profile/confirm', {
    headers,
    data: {
      request_id: randomUUID(),
      expected_revision: revision,
      confirmed: true,
      profile: {
        gender: '女',
        birth: {
          solar_datetime: '1998-03-12 08:15',
          timezone_offset: 8,
          precision: 'exact',
          time_unknown: false,
          time_uncertainty_minutes: 0,
          location: { city: '合成地点', lng: 116.4, lat: 39.9 },
        },
      },
    },
  });
  expect(confirmed.ok(), 'Confirm the existing synthetic profile fixture without logging its payload').toBe(true);
  const caseTitle = 'Q9合成学习计划';
  const newCase = await api.post('/api/cases', {
    headers,
    data: { request_id: randomUUID(), title: caseTitle, goal: '先核对可用时间，再安排一个小步骤' },
  });
  expect(newCase.ok()).toBe(true);
  const { id: caseId } = (await newCase.json()) as { id: string };
  const question = '如何安排这次Q9合成学习计划？';
  const drawn = await api.post('/api/tarot/draws', {
    headers,
    data: {
      idempotency_key: randomUUID(),
      question,
      case_id: caseId,
      subject_id: 'self',
      spread_id: 'reflect3',
      draw_source: 'auto',
      reversals: true,
    },
  });
  expect(drawn.ok()).toBe(true);
  const { draw } = (await drawn.json()) as { draw: { id: string } };
  for (let position = 1; position <= 3; position++) {
    const revealed = await api.post(`/api/tarot/draws/${draw.id}/reveal`, {
      headers,
      data: { request_id: randomUUID(), position },
    });
    expect(revealed.ok()).toBe(true);
  }
  // This preloads a persisted result from the verified local FixtureModel, never
  // ConfiguredModel or a message endpoint. Browser pages remain strictly read-only.
  const read = await api.post(`/api/tarot/draws/${draw.id}/readings`, {
    headers,
    data: { request_id: randomUUID() },
    timeout: 45000,
  });
  expect(read.ok(), 'Preseed a scripted-only saved reading').toBe(true);
  const readings = await api.get(`/api/tarot/draws/${draw.id}/readings`, { headers });
  expect(readings.ok()).toBe(true);
  const versions = (await readings.json()) as { version: number; status: string; result?: { answer?: string } }[];
  expect(
    versions.some((item) => item.version === 1 && item.status === 'success' && Boolean(item.result?.answer)),
    'A real saved synthetic reading must exist before rendering',
  ).toBe(true);
  const chart = await api.get(`/api/chart?date=${fixedDate}`, { headers });
  expect(chart.ok()).toBe(true);
  const value = (await chart.json()) as { day?: { day_ganzhi?: string } };
  expect(Boolean(value.day?.day_ganzhi), 'Filled chart data must exist').toBe(true);
  await fixtureSafety(api);
  return { token, drawId: draw.id, dayLabel: value.day!.day_ganzhi!, caseTitle, question };
}

const test = base.extend<Record<never, never>, { q9Seed: Seed }>({
  q9Seed: [
    async ({ playwright }, use, workerInfo) => {
      const api = await playwright.request.newContext({ baseURL: backend });
      try {
        const seed = await seedOwner(api);
        await writeEvidence(`worker-${workerInfo.workerIndex}.json`, {
          schema: 'frontend-q9-v3-worker-v1',
          worker_index: workerInfo.workerIndex,
          synthetic_owner: true,
          profile: 'existing synthetic fixture, omitted from diagnostics',
          scripted_reading_preseeded: true,
          browser_mutations_allowed: false,
          database: 'core_test_fe',
          model: 'scripted-only',
          real_model_calls: 0,
        });
        await use(seed);
        await fixtureSafety(api);
      } finally {
        await api.dispose();
      }
    },
    { scope: 'worker' },
  ],
});

const viewports = [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
];
for (const viewport of viewports)
  for (const theme of ['light', 'dark'] as const)
    for (const name of names)
      test(`Q9 v3 ${name} ${theme} ${viewport.width}`, async ({ page, q9Seed }) => {
        await page.setViewportSize(viewport);
        const activity = await guardV3(page, name);
        let readinessError = '';
        try {
          await openPopulatedV3(page, name, theme, q9Seed);
        } catch (error) {
          // Do not serialize locator snapshots or form values from the profile page.
          readinessError = error instanceof Error ? error.name : 'ReadinessError';
        }
        await captureV3(page, name, theme, activity, readinessError);
      });
