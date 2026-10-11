"""One deterministic chart bundle for web and Hermes. No generated keywords."""
import argparse
from copy import deepcopy
from functools import lru_cache
import json
import os
import subprocess
import sys
from pathlib import Path
from context_engine import build_context, choose_date

SKILL=Path(__file__).resolve().parent
PYTHON=os.environ.get('CHART_PYTHON',sys.executable if os.name=='nt' else 'python3')

@lru_cache(maxsize=32)
def _run(engine, args, stamp):
    result=subprocess.run([PYTHON,str(SKILL/(engine+'.py'))]+list(args),
                          capture_output=True,text=True,encoding='utf-8',timeout=35)
    if result.returncode:
        raise RuntimeError(engine+' 排盘失败；请检查服务端日志与出生参数')
    return json.loads(result.stdout)

def run(engine,args):
    return _run(engine,tuple(args),(SKILL/(engine+'.py')).stat().st_mtime_ns)

def bundle(arc,date):
    u=arc.get('user',{}); b=u.get('birth',{}); loc=b.get('location',{})
    if not b.get('solar_datetime') or b.get('time_unknown'):
        return {k:{'status':'missing','reason':'缺少可靠出生时刻，不能精确排盘'} for k in ['bazi','ziwei','astro']}
    # Existing Chinese profiles have no offset. Keep their prior +8 convention,
    # disclose that assumption, and never rewrite the stored birth time.
    tz_raw=b.get('timezone_offset',loc.get('timezone_offset'))
    try:
        tz=8.0 if tz_raw is None else float(tz_raw)
        if not -14<=tz<=14: raise ValueError()
    except (ValueError,TypeError):
        return {k:{'status':'missing','reason':'出生时区偏移无效，需提供当时的 UTC 偏移（含夏令时）'} for k in ['bazi','ziwei','astro']}
    common=['--datetime',b['solar_datetime'],'--lng',str(loc.get('lng','')),'--tz',str(tz)]
    result={}
    plans={'bazi':['chart']+common+['--gender',u.get('gender','男')],
           'ziwei':['horoscope']+common+['--gender',u.get('gender','男'),'--date',date],
           'astro':common+['--lat',str(loc.get('lat','')),'--date',date]}
    for engine,args in plans.items():
        try:
            # Cached calculations are shared across requests; annotations must
            # not accumulate or leak one profile's uncertainty into another.
            data=deepcopy(run(engine,args))
            if engine=='bazi':
                data=dict(data,day=run('bazi',['day','--date',date]),
                          target_liuyue=run('bazi',['liuyue','--year',date[:4]]))
                data['method_note']='喜用神为表层计数启发式；流月有月中样本及准确交节区间，当前日期用 day.month_ganzhi；日时柱地方平太阳时，年月柱按真实时刻交节。'
            quality=data.setdefault('quality',{})
            quality['birth_timezone_source']='profile' if tz_raw is not None else 'legacy_default_UTC+8'
            quality['birth_time_uncertainty_minutes']=b.get('time_uncertainty_minutes')
            quality.setdefault('assumptions',[])
            if tz_raw is None:
                quality['assumptions'].append('档案未注明出生时 UTC 偏移，沿用原系统 +8；未自动推断历史夏令时')
            if b.get('time_uncertainty_minutes'):
                quality.setdefault('limitations',[]).append('档案含出生时间误差；当前仅为中心时刻排盘，未计算边界敏感性区间')
            result[engine]={'status':'ok','source':engine+'.py','target_date':date,'data':data}
        except (RuntimeError,ValueError,subprocess.SubprocessError,OSError) as exc:
            result[engine]={'status':'error','reason':str(exc),'target_date':date}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--date')
    p.add_argument('--message',default='今日三盘联动晨报')
    p.add_argument('--archive',default=os.path.expanduser('~/.hermes/zhiming/archive.json'))
    p.add_argument('--base',default=os.environ.get('ZHIMING_BASE'))
    p.add_argument('--channel',default=os.environ.get('ZHIMING_CHANNEL'))
    p.add_argument('--external-id',default=os.environ.get('ZHIMING_EXTERNAL_ID'))
    p.add_argument('--case',action='append')
    p.add_argument('--conversation',default='shared')
    p.add_argument('--sync-hermes',action='store_true')
    p.add_argument('--binding-kind',choices=['user','chat'],default='user')
    a=p.parse_args()
    from context_query import ChannelContext
    adapter=ChannelContext(a.base or Path(a.archive).parent)
    context=adapter.prepare(a.message,a.channel,a.external_id,a.case,a.conversation,with_charts=True,
                            date=a.date,sync=a.sync_hermes,binding_kind=a.binding_kind)
    print(json.dumps(context,ensure_ascii=False,indent=1))
