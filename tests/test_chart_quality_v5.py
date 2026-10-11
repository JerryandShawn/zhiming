import copy
import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hermes'))


class BundleQualityTests(unittest.TestCase):
    def profile(self, **birth):
        return {'user': {'gender': '女', 'birth': dict(
            solar_datetime='1990-05-03 13:18', location={'lng':104.07, 'lat':30.57}, **birth)}}

    def test_timezone_is_passed_without_rewriting_birth_record(self):
        from chart_context import bundle
        arc = self.profile(timezone_offset=5.5, time_uncertainty_minutes=20)
        original = copy.deepcopy(arc)
        calls = []
        def run(engine, args):
            calls.append((engine,args))
            return [] if args[0]=='liuyue' else {}
        with patch('chart_context.run', side_effect=run):
            charts = bundle(arc, '2026-02-01')
        self.assertEqual(arc, original)
        for engine in ('bazi','ziwei','astro'):
            args = next(a for e,a in calls if e==engine and '--datetime' in a)
            self.assertEqual(args[args.index('--tz')+1], '5.5')
            self.assertEqual(charts[engine]['data']['quality']['birth_timezone_source'], 'profile')
            self.assertEqual(charts[engine]['data']['quality']['birth_time_uncertainty_minutes'],20)

    def test_legacy_timezone_assumption_is_visible(self):
        from chart_context import bundle
        with patch('chart_context.run', side_effect=lambda e,a: [] if a[0]=='liuyue' else {}):
            charts = bundle(self.profile(), '2026-02-01')
        self.assertEqual(charts['astro']['data']['quality']['birth_timezone_source'], 'legacy_default_UTC+8')
        self.assertIn('夏令时', charts['astro']['data']['quality']['assumptions'][0])

    def test_invalid_timezone_does_not_silently_default(self):
        from chart_context import bundle
        for bad in ('Europe/London', 99, float('nan')):
            with patch('chart_context.run') as run:
                charts=bundle(self.profile(timezone_offset=bad), '2026-02-01')
            self.assertEqual([c['status'] for c in charts.values()], ['missing']*3)
            run.assert_not_called()

    def test_quality_annotations_do_not_mutate_cached_results(self):
        from chart_context import bundle
        cache={engine:{'quality':{'limitations':['original']}} for engine in ('bazi','ziwei','astro')}
        original=copy.deepcopy(cache)
        def run(engine,args):
            if args[0]=='liuyue': return []
            if args[0]=='day': return {}
            return cache[engine]
        with patch('chart_context.run',side_effect=run):
            first=bundle(self.profile(time_uncertainty_minutes=30),'2026-02-01')
            second=bundle(self.profile(),'2026-02-01')
        self.assertEqual(cache,original)
        self.assertEqual(len(second['astro']['data']['quality']['assumptions']),1)
        self.assertEqual(second['astro']['data']['quality']['limitations'],['original'])


@unittest.skipUnless(importlib.util.find_spec('lunar_python'), 'requires lunar-python')
class BaziQualityTests(unittest.TestCase):
    def chart(self, birth, lng=104.07, tz=8):
        from bazi import cmd_chart
        with patch('bazi._emit') as emit:
            cmd_chart(SimpleNamespace(datetime=birth,lng=lng,tz=tz,gender='男'))
        return emit.call_args.args[0]

    def test_known_pillars_preserved_and_heuristic_declared(self):
        c=self.chart('2012-05-03 13:18')
        self.assertEqual([p['ganzhi'] for p in c['pillars'].values()], ['壬辰','甲辰','甲子','庚午'])
        self.assertFalse(c['method']['equation_of_time_applied'])
        self.assertIn('启发式',c['method']['xiyongshen'])
        self.assertIsNone(c['quality']['prediction_probability'])

    def test_lichun_uses_real_instant_not_longitude_shift(self):
        from lunar_python import Solar
        boundary=Solar.fromYmd(2026,2,10).getLunar().getJieQiTable()['立春']
        instant=datetime.strptime(boundary.toYmdHms(),'%Y-%m-%d %H:%M:%S')
        before=self.chart((instant-timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M'))
        after=self.chart((instant+timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M'))
        self.assertNotEqual(before['pillars']['year']['ganzhi'], after['pillars']['year']['ganzhi'])
        self.assertNotEqual(before['pillars']['month']['ganzhi'], after['pillars']['month']['ganzhi'])
        # Chengdu's longitude correction exceeds 60 minutes; both local mean
        # times precede the Beijing clock's term boundary, but their instants do not.
        self.assertLess(datetime.strptime(after['corrected_time'],'%Y-%m-%d %H:%M:%S'), instant)

    def test_selected_day_does_not_reuse_month_midpoint(self):
        from bazi import cmd_day, _liuyue
        with patch('bazi._emit') as emit:
            cmd_day(SimpleNamespace(date='2026-02-01'))
        day=emit.call_args.args[0]
        middle=_liuyue(2026)[1]
        self.assertNotEqual(day['month_ganzhi'], middle['ganzhi'])
        self.assertLessEqual(day['period_start'],day['sample_at'])
        self.assertLess(day['sample_at'],day['period_end_exclusive'])
        self.assertLessEqual(middle['period_start'],middle['sample_at'])
        self.assertLess(middle['sample_at'],middle['period_end_exclusive'])

    def test_equivalent_civil_instants_produce_same_pillars(self):
        a=self.chart('1990-05-03 13:18',tz=8)
        b=self.chart('1990-05-03 05:18',tz=0)
        self.assertEqual(a['pillars'],b['pillars'])
        self.assertEqual(a['dayun'],b['dayun'])


@unittest.skipUnless(importlib.util.find_spec('swisseph'), 'requires pyswisseph')
class AstroQualityTests(unittest.TestCase):
    def test_birth_offset_is_independent_of_report_day_offset(self):
        from astro import chart
        a=chart('1990-05-03 13:18',104.07,30.57,'2026-09-29',8)
        b=chart('1990-05-03 05:18',104.07,30.57,'2026-09-29',0)
        self.assertEqual(a['utc_time'],b['utc_time'])
        self.assertEqual(a['planets'],b['planets'])
        self.assertEqual(a['transits'],b['transits'])
        self.assertIsNone(a['quality']['prediction_probability'])


@unittest.skipUnless(importlib.util.find_spec('py_iztro'), 'requires py-iztro')
class ZiweiQualityTests(unittest.TestCase):
    def test_solar_hour_mapping_and_declared_conventions(self):
        from ziwei import build,natal,hour_to_index
        self.assertEqual([hour_to_index(h) for h in (0,1,22,23)],[0,1,11,12])
        a,c=build(datetime(1990,5,3,13,18),104.07,'女',8)
        b,d=build(datetime(1990,5,3,5,18),104.07,'女',0)
        self.assertEqual(c,d)
        result=natal(a,c)
        self.assertEqual(result['palaces'],natal(b,d)['palaces'])
        self.assertFalse(result['method']['equation_of_time_applied'])
        self.assertEqual(len(result['palaces'][0]['linked_palaces']),3)


if __name__=='__main__': unittest.main(verbosity=2)
