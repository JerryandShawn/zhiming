#!/usr/bin/env python3
"""Swiss Ephemeris natal houses, aspects and dated transits (civil time -> UTC)."""
import argparse
import json
import math
from datetime import datetime, timedelta
import swisseph as swe

SIGNS = ['白羊','金牛','双子','巨蟹','狮子','处女','天秤','天蝎','射手','摩羯','水瓶','双鱼']
BODIES = [('太阳',swe.SUN),('月亮',swe.MOON),('水星',swe.MERCURY),('金星',swe.VENUS),
          ('火星',swe.MARS),('木星',swe.JUPITER),('土星',swe.SATURN),
          ('天王',swe.URANUS),('海王',swe.NEPTUNE),('冥王',swe.PLUTO)]
ASPECTS = [('合相',0),('六合',60),('刑相',90),('拱相',120),('冲相',180)]

def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name+'必须是有限数值')
    return value

def fmt(lon):
    finite(lon,'黄经')
    lon %= 360
    return {'sign':SIGNS[int(lon//30)], 'deg':round(lon%30,2), 'longitude':round(lon,5)}

def julian(dt):
    return finite(swe.julday(dt.year,dt.month,dt.day,dt.hour+dt.minute/60+dt.second/3600),'儒略日')

def house_of(lon, cusps):
    for i, start in enumerate(cusps):
        if (lon-start)%360 < (cusps[(i+1)%12]-start)%360:
            return i+1
    return None

def positions(jd, cusps):
    result = {}
    for name, body in BODIES:
        xx, flags = swe.calc_ut(jd, body, swe.FLG_MOSEPH | swe.FLG_SPEED)
        for value in xx:
            finite(value, '历表返回值')
        result[name] = dict(fmt(xx[0]), house=house_of(xx[0],cusps),
                            retrograde=xx[3]<0, speed=round(xx[3],5), returned_flags=int(flags))
    return result

def aspects(left, right=None, orb=6):
    finite(orb,'相位容许度')
    if not 0 <= orb <= 180: raise ValueError('相位容许度超出范围')
    result=[]
    for i,(a,p) in enumerate(left.items()):
        targets=list(right.items()) if right is not None else list(left.items())[i+1:]
        for b,q in targets:
            finite(p['longitude'],'天体黄经'); finite(q['longitude'],'天体黄经')
            separation=abs((p['longitude']-q['longitude']+180)%360-180)
            for label,angle in ASPECTS:
                error=abs(separation-angle)
                if error<=orb:
                    result.append({'from':a,'to':b,'aspect':label,'angle':angle,'orb':round(error,3)})
    return sorted(result,key=lambda x:x['orb'])

def chart(birth,lng,lat,date=None,tz=8,target_tz=8):
    for name,value in [('经度',lng),('纬度',lat),('时区',tz),('目标时区',target_tz)]: finite(value,name)
    if not (-180<=lng<=180 and -90<lat<90 and -14<=tz<=14 and -14<=target_tz<=14):
        raise ValueError('出生经纬度或时区超出范围')
    civil=datetime.strptime(birth,'%Y-%m-%d %H:%M')
    utc=civil-timedelta(hours=tz)
    jd=julian(utc)
    cusps,angles=swe.houses_ex(jd,lat,lng,b'P')
    if len(cusps) != 12: raise ValueError('Placidus没有返回12个宫头')
    for value in (*cusps,*angles): finite(value,'宫制返回值')
    planets=positions(jd,cusps)
    result={'engine_version':'astro-core-3.1','civil_time':birth,'utc_time':utc.isoformat()+'Z',
            'timezone_offset':tz,'time_basis':'出生地民用时间减时区；不重复经度修正',
            'house_system':'Placidus','ephemeris':'Moshier','planets':planets,
            'asc':fmt(angles[0]),'mc':fmt(angles[1]),
            'houses':[dict(fmt(lon),house=i+1) for i,lon in enumerate(cusps)],
            'aspects':aspects(planets),'aspect_orb':6,
            'method':{'zodiac':'tropical','coordinates':'geocentric ecliptic longitude',
                      'aspects':'0/60/90/120/180 度，本命统一容许度 6 度，行运 2 度',
                      'houses':'Placidus；行星宫位按黄经落入宫头区间，不含行星黄纬修正',
                      'birth_timezone':'显式固定 UTC 偏移；不自动推断历史夏令时',
                      'time_scale':'民用 UTC 近似作为 UT 输入 swe.calc_ut/houses_ex'},
            'quality':{'calculation':'astronomical_positions_with_declared_conventions',
                       'prediction_probability':None,
                       'limitations':['天体位置计算可复核，不等于占星解释有事件预测效度',
                                      '出生时间或时区误差影响上升、宫位及月亮位置',
                                      '统一容许度是本项目规则，不代表各占星流派共识',
                                      '未计算行运精确入相、出相、太阳弧或次限']}}
    if date:
        target=datetime.strptime(date,'%Y-%m-%d').replace(hour=12)
        moving=positions(julian(target-timedelta(hours=target_tz)),cusps)
        result['transits']={'date':date,'sample_time':target.isoformat(),
            'timezone_offset':target_tz,'house_reference':'本命宫位','orb_limit':2,
            'planets':moving,'natal_reference':planets,'aspects_to_natal':aspects(moving,planets,2),
            'precision_note':'当日12时快照，不代表精确入相/出相时间；未计算太阳弧或次限'}
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--datetime',required=True)
    p.add_argument('--lng',type=float,required=True)
    p.add_argument('--lat',type=float,required=True)
    p.add_argument('--date')
    p.add_argument('--tz',type=float,default=8)
    p.add_argument('--target-tz',type=float,default=8,help='行运日期所在 UTC 偏移，默认报告时间 +8')
    a=p.parse_args()
    print(json.dumps(chart(a.datetime,a.lng,a.lat,a.date,a.tz,a.target_tz),ensure_ascii=False,indent=1,allow_nan=False))

if __name__=='__main__': main()
