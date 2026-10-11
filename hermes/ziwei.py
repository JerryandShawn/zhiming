#!/usr/bin/env python3
"""知命紫微排盘引擎：确定性计算，输出 JSON。AI 只解读，不计算。
用法：
  python3 ziwei.py chart     --datetime "2012-05-03 13:18" --lng 104.07 --gender 男
  python3 ziwei.py horoscope --datetime "2012-05-03 13:18" --lng 104.07 --gender 男 --date 2026-08-13
"""
import argparse, json, sys, site
from datetime import datetime, timedelta
sys.path.insert(0, site.getusersitepackages())
from py_iztro import Astro

def hour_to_index(h):
    if h == 23: return 12          # 晚子时
    return ((h + 1) // 2) % 12     # 0=早子 1=丑 ... 11=亥

def star(s):
    d = {"name": s.name}
    if getattr(s, "brightness", ""): d["brightness"] = s.brightness
    if getattr(s, "mutagen", ""):    d["mutagen"] = s.mutagen
    return d

def palace(p):
    return {"name": p.name, "ganzhi": p.heavenly_stem + p.earthly_branch,
            "is_body": p.is_body_palace, "is_laiyin": p.is_original_palace,
            "major": [star(s) for s in p.major_stars],
            "minor": [star(s) for s in p.minor_stars],
            "decadal": {"range": list(p.decadal.range),
                        "ganzhi": p.decadal.heavenly_stem + p.decadal.earthly_branch},
            "ages": p.ages}

def build(dt, lng, gender, tz=8):
    if not -180 <= lng <= 180 or not -14 <= tz <= 14:
        raise ValueError('出生经度或时区超出范围')
    c = dt + timedelta(minutes=(lng - tz * 15) * 4)  # 地方平太阳时，未计均时差
    a = Astro().by_solar(f"{c.year}-{c.month}-{c.day}", hour_to_index(c.hour), gender)
    return a, c

def natal(a, c):
    palaces = [palace(p) for p in a.palaces]
    for i, p in enumerate(palaces):
        p['index'] = i
        p['linked_palaces'] = [{'index': j, 'relation': relation,
                               'name': palaces[j]['name'], 'ganzhi': palaces[j]['ganzhi'],
                               'major': palaces[j]['major'], 'minor': palaces[j]['minor']}
                              for j, relation in [((i+4)%12,'三合'),((i+8)%12,'三合'),((i+6)%12,'对宫')]]
    return {"corrected_time": c.strftime("%Y-%m-%d %H:%M"),
            "engine_version": "ziwei-5.0",
            "time_basis": "地方平太阳时：仅经度修正，未计均时差；不是完整真太阳时",
            "method": {"calendar": "py-iztro by_solar 默认历法与闰月规则",
                       "hour_index": hour_to_index(c.hour),
                       "late_zi": "23:00 单独编码为 12，由 py-iztro 默认日界规则处理",
                       "equation_of_time_applied": False,
                       "links": "本宫的两组三合宫及对宫；四化按真实星曜位置关联本命宫和运限宫"},
            "quality": {"calculation": "deterministic_convention", "prediction_probability": None,
                        "limitations": ["采用当前 py-iztro 默认流派，未做不同流派交叉校盘",
                                        "宫位关联与四化是传统盘面结构，不代表事件已发生或必然发生",
                                        "出生时刻靠近时辰或日界时，时间误差可能改变命盘"]},
            "lunar_date": a.chinese_date, "zodiac": a.zodiac, "sign": a.sign,
            "wuxing_ju": a.five_elements_class,
            "ming_gong": a.earthly_branch_of_soul_palace,
            "shen_gong": a.earthly_branch_of_body_palace,
            "ming_zhu": a.soul, "shen_zhu": a.body,
            "palaces": palaces}

def scope(h):
    return {"name": h.name, "ganzhi": h.heavenly_stem + h.earthly_branch,
            "index": h.index, "mutagen": h.mutagen, "palace_names": h.palace_names}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["chart", "horoscope"])
    ap.add_argument("--datetime", required=True)
    ap.add_argument("--lng", type=float, required=True)
    ap.add_argument("--gender", required=True, choices=["男", "女"])
    ap.add_argument("--date")
    ap.add_argument("--tz", type=float, default=8, help="出生时 UTC 偏移，须已包含当时夏令时")
    a_ = ap.parse_args()
    dt = datetime.strptime(a_.datetime, "%Y-%m-%d %H:%M")
    ast, c = build(dt, a_.lng, a_.gender, a_.tz)
    r = natal(ast, c)
    r['timezone_offset'] = a_.tz
    if a_.cmd == "horoscope":
        d = a_.date or datetime.now().strftime("%Y-%m-%d")
        h = ast.horoscope(d)
        r["horoscope"] = {"target_date": d, "lunar": h.lunar_date,
                          "decadal": scope(h.decadal), "yearly": scope(h.yearly),
                          "monthly": scope(h.monthly), "daily": scope(h.daily)}
        for level in ('decadal', 'yearly', 'monthly', 'daily'):
            layer = r['horoscope'][level]
            layer['mutagen_links'] = []
            for label, name in zip(('禄','权','科','忌'), layer['mutagen']):
                for p in r['palaces']:
                    if any(s['name'] == name for s in p['major'] + p['minor']):
                        layer['mutagen_links'].append({'star': name, 'mutagen': label,
                            'natal_palace': p['name'], 'palace_index': p['index'],
                            'scope_palace': layer['palace_names'][p['index']]})
    print(json.dumps(r, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
