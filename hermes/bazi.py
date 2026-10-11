#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知命体系 · 八字排盘工具 bazi.py

子命令：
  chart  --datetime "YYYY-MM-DD HH:MM" [--lng 经度] [--gender 男|女]   排全盘（JSON）
  day    --date YYYY-MM-DD                                            当日流日干支
  liuyue --year YYYY                                                  该年 12 流月

依赖：lunar-python（pip install lunar-python）
日时柱采用地方平太阳时（仅经度修正，不含均时差）；年月柱按真实时刻交节。
测试向量：2012-05-03 13:18 成都（经度 104.07）男 → 壬辰/甲辰/甲子/庚午
"""
import argparse
import json
import math
import sys
from datetime import datetime, timedelta

from lunar_python import Solar
from lunar_python.util import LunarUtil

# 天干、地支五行
WU_GAN = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
          "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
WU_ZHI = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
          "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
WUXING = ["金", "木", "水", "火", "土"]
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}  # 我生者
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}      # 我克者


def _sheng_wo(wx):
    """生我者（印）"""
    for k, v in SHENG.items():
        if v == wx:
            return k


def _ke_wo(wx):
    """克我者（官杀）"""
    for k, v in KE.items():
        if v == wx:
            return k


def _emit(obj):
    s = json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(s)


def _pillar(ganzhi, shishen_gan, shishen_zhi, nayin):
    gan, zhi = ganzhi[0], ganzhi[1]
    # 地支十神取本气（藏干第一位）
    if isinstance(shishen_zhi, list):
        shishen_zhi = shishen_zhi[0] if shishen_zhi else ""
    return {
        "ganzhi": ganzhi,
        "gan": gan,
        "zhi": zhi,
        "wuxing_gan": WU_GAN[gan],
        "wuxing_zhi": WU_ZHI[zhi],
        "shishen_gan": shishen_gan,
        "shishen_zhi": shishen_zhi,
        "nayin": nayin,
    }


def _wuxing_count(pillars):
    count = {w: 0 for w in WUXING}
    for p in pillars.values():
        count[p["wuxing_gan"]] += 1
        count[p["wuxing_zhi"]] += 1
    return count


def _xiyongshen(dm_wx, count, month_zhi_wx):
    """喜用神简易启发式：身弱取生扶（印+比劫），身强取克泄耗（官杀+食伤+财）。
    力量持平时看月令：月令生扶日主则按身强，否则按身弱。"""
    support = count[_sheng_wo(dm_wx)] + count[dm_wx]
    restrain = 8 - support
    if support > restrain:
        strong = True
    elif support < restrain:
        strong = False
    else:
        strong = month_zhi_wx in (_sheng_wo(dm_wx), dm_wx)
    if strong:
        return [_ke_wo(dm_wx), SHENG[dm_wx], KE[dm_wx]]
    return [_sheng_wo(dm_wx), dm_wx]


def _liuyue(year):
    """公历各月中旬样本及其节月区间；month 是样本索引，不是节月起点。"""
    rows = []
    for month in range(1, 13):
        sample = Solar.fromYmdHms(year, month, 15, 12, 0, 0)
        lunar = sample.getLunar()
        rows.append(dict(month="%04d-%02d" % (year, month),
                         ganzhi=lunar.getMonthInGanZhiExact(),
                         sample_at=sample.toYmdHms(), **_jie_interval(lunar)))
    return rows


def _liunian(year):
    """Requested-year samples with real Li-Chun boundaries, never host current year."""
    rows = []
    for value in range(year - 2, year + 8):
        sample = Solar.fromYmdHms(value, 6, 1, 12, 0, 0)
        lunar = sample.getLunar()
        start = lunar.getJieQiTable()["立春"]
        end = Solar.fromYmd(value + 1, 6, 1).getLunar().getJieQiTable()["立春"]
        rows.append({"year": value, "ganzhi": lunar.getYearInGanZhiExact(),
                     "sample_at": sample.toYmdHms(), "timezone_offset": 8,
                     "period_start": start.toYmdHms(), "period_end_exclusive": end.toYmdHms(),
                     "precision_note": "立春至次年立春的节年；公历年初可能仍属上一节年"})
    return rows


def _jie_interval(lunar):
    prev_jie, next_jie = lunar.getPrevJie(), lunar.getNextJie()
    return {"period_start": prev_jie.getSolar().toYmdHms(),
            "period_end_exclusive": next_jie.getSolar().toYmdHms(),
            "start_jie": prev_jie.getName(), "end_jie": next_jie.getName(),
            "timezone_offset": 8}


def _solar(dt):
    return Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def _relative_pillar(ganzhi, day_master):
    """Use one day master even when the civil and local-solar dates differ."""
    hidden = LunarUtil.ZHI_HIDE_GAN[ganzhi[1]]
    return _pillar(ganzhi, LunarUtil.SHI_SHEN[day_master + ganzhi[0]],
                   [LunarUtil.SHI_SHEN[day_master + gan] for gan in hidden],
                   LunarUtil.NAYIN[ganzhi])


def cmd_chart(a):
    civil = datetime.strptime(a.datetime, "%Y-%m-%d %H:%M")
    tz = getattr(a, 'tz', 8)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in (a.lng, tz)) or not -180 <= a.lng <= 180 or not -14 <= tz <= 14:
        raise ValueError('出生经度或时区超出范围')
    if getattr(a, "gender", None) not in ("男", "女", "male", "female", "m", "f", "M", "F", "1", "0"):
        raise ValueError("缺少已明确提供的性别计算参数，不能默认男或女")
    # 地方平太阳时只决定此项目采用的日/时柱口径。节气是同一个真实时刻，
    # 不能把经度偏移误当成节气发生时刻也移动；lunar-python 节气表使用 UTC+8。
    dt = civil + timedelta(minutes=(a.lng - tz * 15) * 4)
    calendar_dt = civil + timedelta(hours=8-tz)
    solar = _solar(dt)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    ec.setSect(2)
    calendar_ec = _solar(calendar_dt).getLunar().getEightChar()

    pillars = {
        "year": _relative_pillar(calendar_ec.getYear(), ec.getDayGan()),
        "month": _relative_pillar(calendar_ec.getMonth(), ec.getDayGan()),
        "day": _pillar(ec.getDay(), ec.getDayShiShenGan(),
                       ec.getDayShiShenZhi(), ec.getDayNaYin()),
        "hour": _pillar(ec.getTime(), ec.getTimeShiShenGan(),
                        ec.getTimeShiShenZhi(), ec.getTimeNaYin()),
    }
    day_master = pillars["day"]["gan"]
    dm_wx = WU_GAN[day_master]
    count = _wuxing_count(pillars)

    gender = 1 if a.gender in ("男", "male", "m", "M", "1") else 0
    yun = calendar_ec.getYun(gender, 1)
    dayun = [{"ganzhi": d.getGanZhi(), "start_age": d.getStartAge(),
              "start_year": d.getStartYear(), "end_year": d.getEndYear()}
             for d in yun.getDaYun(11) if d.getGanZhi()][:10]

    target = datetime.strptime(getattr(a, "date", None) or civil.strftime("%Y-%m-%d"), "%Y-%m-%d")
    liunian = _liunian(target.year)

    _emit({
        "solar_datetime": a.datetime,
        "corrected_time": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone_offset": tz,
        "time_basis": "日时柱采用地方平太阳时（仅经度修正，未计均时差）；年月柱及起运按同一真实时刻交节",
        "engine_version": "bazi-core-3.1",
        "target_date": target.strftime("%Y-%m-%d"),
        "method": {"calendar": "lunar-python EightChar", "day_sect": 2,
                   "year_boundary": "立春准确时刻，UTC+8 节气表",
                   "month_boundary": "节交接准确时刻，UTC+8 节气表",
                   "dayun_sect": 1, "equation_of_time_applied": False,
                   "xiyongshen": "表层八字五行计数启发式，不是完整格局/调候分析"},
        "quality": {"calculation": "deterministic_convention", "prediction_probability": None,
                    "limitations": ["五行数量不等于实际力量；未计藏干权重、通根、合化及调候",
                                    "喜用神仅为探索线索，不可单独作为行动建议或吉凶结论",
                                    "出生时刻误差及日界流派可能改变日时柱；未估计出生时间误差"]},
        "lunar_datetime": "%s年%s月%s" % (lunar.getYearInGanZhi(),
                                        lunar.getMonthInChinese(),
                                        lunar.getDayInChinese()),
        "pillars": pillars,
        "day_master": day_master,
        "day_master_wuxing": dm_wx,
        "wuxing_count": count,
        "xiyongshen": _xiyongshen(dm_wx, count, pillars["month"]["wuxing_zhi"]),
        "dayun": dayun,
        "liunian": liunian,
        "liuyue": _liuyue(target.year),
    })


def cmd_day(a):
    d = datetime.strptime(a.date, "%Y-%m-%d")
    solar = Solar.fromYmdHms(d.year, d.month, d.day, 12, 0, 0)
    lunar = solar.getLunar()
    _emit({"date": a.date, "day_ganzhi": lunar.getDayInGanZhi(),
           "year_ganzhi": lunar.getYearInGanZhiExact(),
           "month_ganzhi": lunar.getMonthInGanZhiExact(),
           "sample_at": solar.toYmdHms(), **_jie_interval(lunar),
           "method_note": "所选日期 UTC+8 正午快照；交节日年/月柱在节气时刻前后可能不同"})


def cmd_liuyue(a):
    _emit(_liuyue(a.year))


def main():
    p = argparse.ArgumentParser(prog="bazi.py",
                                description="知命体系·八字排盘工具（lunar-python）")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("chart", help="排全盘")
    c.add_argument("--datetime", required=True, help='阳历 "YYYY-MM-DD HH:MM"')
    c.add_argument("--lng", type=float, required=True,
                   help="出生地经度，地方平太阳时修正（不含均时差）")
    c.add_argument("--tz", type=float, required=True, help="出生民用时间的 UTC 偏移，需已包含当时夏令时")
    c.add_argument("--gender", required=True, choices=("男", "女"), help="男/女，定大运顺逆")
    c.add_argument("--date", help="目标日期；未指定时只使用出生日期，绝不使用机器当前年份")

    d = sub.add_parser("day", help="流日干支")
    d.add_argument("--date", required=True, help="YYYY-MM-DD")

    m = sub.add_parser("liuyue", help="指定年份 12 流月")
    m.add_argument("--year", type=int, required=True)

    a = p.parse_args()
    if a.cmd == "chart":
        cmd_chart(a)
    elif a.cmd == "day":
        cmd_day(a)
    else:
        cmd_liuyue(a)


if __name__ == "__main__":
    main()
