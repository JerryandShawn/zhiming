import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from multiprocessing import Process

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'hermes'))
sys.path.insert(0,str(ROOT))
from archive_store import transaction, read_json, deep_merge, atomic_write
from context_engine import build_context, choose_date
from report_store import store

def writer(path,n):
    for i in range(20):
        transaction(path,lambda d:d['rows'].append([n,i]),{'rows':[]})

class StorageTests(unittest.TestCase):
    def test_concurrent_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'archive.json')
            processes=[Process(target=writer,args=(path,i)) for i in range(4)]
            for p in processes:p.start()
            for p in processes:p.join(20);self.assertEqual(p.exitcode,0)
            self.assertEqual(len(read_json(path)['rows']),80)

    def test_report_retry_and_daily_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'archive.json')
            store(path,'2026-09-28','晨报','已验证格式内容'*50)
            store(path,'2026-09-28','晨报','更新后的完整报告'*50)
            arc=read_json(path)
            self.assertEqual(len(arc['reports']),1)
            self.assertIn('更新后',arc['reports'][0]['content'])
            with self.assertRaises(ValueError):store(path,'2026-09-28','晨报','半截')
            deep_merge(arc,{'daily_log':[{'date':'2026-09-28','questions':[{'q':'a'}]}]})
            deep_merge(arc,{'daily_log':[{'date':'2026-09-28','questions':[{'q':'b'}]}]})
            self.assertEqual(len(arc['daily_log']),1)
            self.assertEqual(len(arc['daily_log'][0]['questions']),2)

class ContextTests(unittest.TestCase):
    def test_continuity_retrieval_budget(self):
        arc={'user':{'name':'test'},'conversation_state':{'boarding':'已更正为走读'},
             'calibration':{'notes':'旧判断失准'},'daily_log':[{'date':'2026-09-01','text':'学业摸底反馈'*400} for _ in range(300)],
             'reports':[{'date':'2026-09-20','content':'学业总结'*5000}]}
        history=[{'role':'user' if i%2==0 else 'assistant','content':'继续学业分析'*1000,'source':'feishu','at':str(i)} for i in range(100)]
        context,messages=build_context(arc,'学业如何',history,{'astro':{'status':'error','reason':'缺资料'}})
        self.assertEqual(context['layers']['continuity']['boarding'],'已更正为走读')
        self.assertLessEqual(context['meta']['characters'],60000)
        self.assertLessEqual(sum(len(x['content']) for x in messages),12000)
        self.assertEqual(context['meta']['chart_status']['astro'],'error')
        self.assertIn('reports',context['meta']['sources'])

    def test_dates(self):
        self.assertEqual(choose_date('分析2026-10-01'),'2026-10-01')
        with self.assertRaises(ValueError):choose_date('分析2026-02-31')

class ChartTests(unittest.TestCase):
    def test_utc_and_house_aspect_math(self):
        from astro import chart, aspects, house_of
        c=chart('2012-05-03 13:18',104.07,30.57,'2026-09-28')
        self.assertEqual(c['utc_time'],'2012-05-03T05:18:00Z')
        self.assertEqual(len(c['houses']),12)
        self.assertEqual(len(c['planets']),10)
        self.assertTrue(all(1<=p['house']<=12 for p in c['planets'].values()))
        self.assertTrue(all(x['orb']<=2 for x in c['transits']['aspects_to_natal']))
        self.assertEqual(aspects({'a':{'longitude':359},'b':{'longitude':1}})[0]['orb'],2)
        self.assertEqual(house_of(0,[350]+list(range(20,350,30))),1)

    def test_three_charts_date_changes(self):
        from chart_context import bundle
        arc={'user':{'birth':{'solar_datetime':'2012-05-03 13:18','location':{'lng':104.07,'lat':30.57}},'gender':'男'}}
        a=bundle(arc,'2026-09-28'); b=bundle(arc,'2026-09-29')
        self.assertEqual([x['status'] for x in a.values()],['ok']*3)
        self.assertEqual([p['ganzhi'] for p in a['bazi']['data']['pillars'].values()],['壬辰','甲辰','甲子','庚午'])
        p=a['ziwei']['data']['palaces'][0]
        self.assertEqual([v['index'] for v in p['linked_palaces']],[4,8,6])
        self.assertNotEqual(a['ziwei']['data']['horoscope']['daily']['ganzhi'],b['ziwei']['data']['horoscope']['daily']['ganzhi'])
        self.assertNotEqual(a['astro']['data']['transits']['planets']['月亮'],b['astro']['data']['transits']['planets']['月亮'])
        self.assertTrue(a['ziwei']['data']['horoscope']['daily']['mutagen_links'])

if __name__=='__main__':unittest.main(verbosity=2)
