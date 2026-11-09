import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';

const pick = (value, keys) =>
  Object.fromEntries(keys.filter((key) => Object.hasOwn(value ?? {}, key)).map((key) => [key, value[key]]));

// Resolve document IDs and RFC 6901 pointers. Never infer the primary chart by its array position.
export function readRef(sample, ref) {
  const doc = sample.documents.find((item) => item.document_id === ref.document_id);
  if (!doc) throw new Error('Unknown sample document');
  let value = doc.payload;
  if (ref.path === '') return value;
  if (!ref.path.startsWith('/')) throw new Error('Invalid sample pointer');
  for (const encoded of ref.path.slice(1).split('/')) {
    if (/~(?![01])/.test(encoded)) throw new Error('Invalid pointer escape');
    const key = encoded.replace(/~1/g, '/').replace(/~0/g, '~');
    if (Array.isArray(value) && !/^(0|[1-9][0-9]*)$/.test(key)) throw new Error('Invalid array index');
    if (value === null || typeof value !== 'object' || !Object.hasOwn(value, key))
      throw new Error('Missing sample field');
    value = value[key];
  }
  return value;
}

export function projectSample(sample, tab, sourceSha256) {
  if (sample.view.primary.length !== 1) throw new Error('Expected one explicitly declared primary chart');
  const primary = readRef(sample, sample.view.primary[0]);
  const payload = sample.documents.find((item) => item.kind === 'time_basis')?.payload;
  if (!payload) throw new Error('Missing time basis document');
  let data;
  if (tab === 'bazi') {
    const decade = primary.p8?.decade_luck ?? {};
    data = {
      pillars: primary.pillars,
      p8: {
        decade_luck: {
          ...pick(decade, ['method', 'school', 'source', 'limits', 'forward', 'start_age', 'precision', 'warning']),
          decades: (decade.decades ?? []).map((item) =>
            pick(item, [
              'index',
              'ganzhi',
              'stem_ten_god',
              'hidden_ten_gods',
              'natal_relations',
              'transformation_established',
              'legacy_start_age',
              'legacy_end_age',
              'legacy_start_year',
              'legacy_end_year',
              'start_year',
              'end_year',
              'start_age',
            ]),
          ),
        },
        calendar_layers: { day: { sample_at: primary.p8?.calendar_layers?.day?.sample_at } },
      },
    };
  } else if (tab === 'ziwei') {
    data = pick(primary, [
      'palaces',
      'ming_gong',
      'shen_gong',
      'ming_zhu',
      'shen_zhu',
      'wuxing_ju',
      'method',
      'quality',
      'engine_version',
      'time_basis',
    ]);
  } else if (tab === 'astro') {
    data = pick(primary, [
      'planets',
      'asc',
      'mc',
      'houses',
      'aspects',
      'house_system',
      'method',
      'quality',
      'engine_version',
      'ephemeris',
      'time_basis',
    ]);
  } else throw new Error('Unknown chart system');
  const basis = {
    time_basis: pick(payload.time_basis, [
      'requires_confirmation',
      'selected_basis',
      'hour_pillar_stable',
      'all_pillars_stable',
    ]),
    interpretation: pick(payload.interpretation, [
      'primary_basis',
      'comparison_basis',
      'comparison_utc_offset_minutes',
      'show_comparison_when_results_differ',
      'western_astrology_basis',
      'primary_chart_ids',
      'comparisons',
      'physical_instant_confirmation_required',
    ]),
    charts: payload.charts.map((chart) => ({
      id: chart.id,
      time_basis: pick(chart.time_basis, ['basis', 'instant_id', 'requires_confirmation']),
      data: { pillars: chart.data?.pillars },
      ziwei_column: pick(chart.ziwei_column, ['ming_gong', 'shen_gong', 'wuxing_ju']),
    })),
  };
  return { data, basis, sourceSha256 };
}

export async function prepareChartSamples(
  sourceDirectory = resolve(
    dirname(fileURLToPath(import.meta.url)),
    '../../../zhiming-v4-p8/docs/v4/contracts/samples',
  ),
) {
  const result = {};
  for (const tab of ['bazi', 'ziwei', 'astro']) {
    const bytes = await readFile(resolve(sourceDirectory, `ayuan_${tab}.json`));
    result[tab] = projectSample(
      JSON.parse(bytes.toString('utf8')),
      tab,
      createHash('sha256').update(bytes).digest('hex'),
    );
  }
  const output = resolve(dirname(fileURLToPath(import.meta.url)), '../src/night/charts/samples.json');
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, `${JSON.stringify(result)}\n`);
  return result;
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  await prepareChartSamples(process.argv[2]);
