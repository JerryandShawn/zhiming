"""Real Charts ephemeris tests using only public synthetic epochs and cached NASA data."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import UTC, datetime, timedelta
from math import atan2, cos, degrees, pi, radians, sin, tan
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.astro_ephemeris import (  # noqa: E402
    Ephemeris,
    actual_utc,
    signed_angle,
)
from mingjing_core.adapters.charts.astro_progressions import secondary_progressions  # noqa: E402
from mingjing_core.adapters.charts.astro_returns import _find_return, solar_return  # noqa: E402
from mingjing_core.adapters.charts.interactions_transits import transit_windows  # noqa: E402

BIRTH = "2000-01-01T12:00:00Z"
TARGET = "2000-12-31T17:48:46.08Z"


def _fixture() -> dict:
    return json.loads((ROOT / "tests/v4/fixtures/p8_astro_horizons.json").read_text(encoding="utf-8"))


def _at(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%b-%d %H:%M").replace(tzinfo=UTC)


class CrossingStub:
    def __init__(self, oscillating: bool) -> None:
        self.oscillating = oscillating

    def julian(self, moment: datetime) -> tuple[float, float]:
        days = moment.timestamp() / 86400
        return days, days

    def position(self, body: str, jd_ut: float) -> dict:
        return {"longitude": (10 * sin((jd_ut + 0.3) * 2 * pi / 3)) % 360 if self.oscillating else 45}


class AstroNative(unittest.TestCase):
    def test_all_sixteen_independent_nasa_positions(self) -> None:
        engine = Ephemeris()
        rows = _fixture()["positions"]
        self.assertEqual(len(rows), 16)
        for row in rows:
            result = engine.position(row["body"], engine.julian(_at(row["at_UTC"]))[1])
            self.assertLess(abs(signed_angle(result["longitude"], row["longitude"])) * 3600, 1.5)
            self.assertLess(abs(result["latitude"] - row["latitude"]) * 3600, 1.5)
            self.assertEqual(result["returned_flags"], 260)

    def test_day_for_year_maps_fractional_age_without_rounding(self) -> None:
        result = secondary_progressions(BIRTH, TARGET)
        progressed_at = actual_utc(result["symbolic_ephemeris_at_UTC"])
        expected = datetime(2000, 1, 2, 12, tzinfo=UTC)
        self.assertLess(abs((progressed_at - expected).total_seconds()), 0.002)
        self.assertIsNone(result["houses"])
        self.assertEqual(len(result["progressed_planets"]), 10)
        # The input spans one *UTC* tropical year; UT1 length differs by sub-second DUT1 change.
        self.assertAlmostEqual(result["mapping"]["age_in_tropical_years"], 1, delta=2e-8)

    def test_progressed_positions_match_independent_nasa(self) -> None:
        result = secondary_progressions(BIRTH, TARGET)
        for row in _fixture()["positions"]:
            if row["at_UTC"] == "2000-Jan-02 12:00":
                observed = result["progressed_planets"][row["body"]]["longitude"]
                self.assertLess(abs(signed_angle(observed, row["longitude"])) * 3600, 1.5)

    def test_zero_age_preserves_all_planets_and_real_time(self) -> None:
        result = secondary_progressions(BIRTH, BIRTH)
        self.assertEqual(result["natal_planets"], result["progressed_planets"])
        self.assertEqual(result["mapping"]["age_in_tropical_years"], 0)

    def test_previous_swiss_tidal_and_delta_t_settings_do_not_leak(self) -> None:
        birth, target = "1800-01-01T12:00:00Z", "1825-01-01T12:00:00Z"
        expected = secondary_progressions(birth, target)
        previous = Ephemeris()
        previous.swe.set_tid_acc(previous.swe.TIDAL_DE200)
        previous.swe.set_delta_t_userdef(100 / 86400)
        actual = secondary_progressions(birth, target)
        self.assertEqual(expected, actual)
        self.assertEqual(actual["metadata"]["tidal_acceleration_arcsec_per_century_squared"], -25.58)

    def test_timezone_aliases_do_not_apply_solar_longitude_correction(self) -> None:
        utc = secondary_progressions(BIRTH, TARGET)
        local = secondary_progressions("2000-01-01T20:00:00+08:00", "2001-01-01T01:48:46.08+08:00")
        self.assertEqual(utc, local)

    def test_reverse_and_excessive_age_rejected(self) -> None:
        for target in ("1999-12-31T12:00:00Z", "2151-01-01T12:00:00Z"):
            with self.assertRaises(ValueError):
                secondary_progressions(BIRTH, target)

    def test_unaware_outside_and_nonstring_times_rejected(self) -> None:
        for value in (None, True, "2000-01-01T12:00", "1799-01-01T00:00:00Z", "bad_private_input"):
            with self.assertRaisesRegex(ValueError, "西占时刻") as context:
                secondary_progressions(value, TARGET)
            self.assertNotIn("bad_private_input", str(context.exception))

    def test_solar_root_agrees_with_separate_swiss_crossing_algorithm(self) -> None:
        result = solar_return(BIRTH, 2025, longitude=116.4, latitude=39.9)
        engine = Ephemeris()
        start = engine.julian(datetime(2024, 12, 27, tzinfo=UTC))[1]
        reference = engine.swe.solcross_ut(result["natal_sun_longitude"], start, engine.flags)
        self.assertLess(abs(reference - result["root"]["return_jd_ut1"]) * 86400, 0.02)
        self.assertLess(result["root"]["residual_degrees"], 2e-7)
        self.assertLessEqual(result["root"]["bracket_seconds"], 0.02)

    def test_ambiguous_or_missing_return_roots_refused(self) -> None:
        for oscillating in (False, True):
            with self.assertRaisesRegex(ValueError, "未找到唯一"):
                _find_return(CrossingStub(oscillating), 0, actual_utc(BIRTH))

    def test_solar_return_independent_nasa_interpolation(self) -> None:
        rows = [row for row in _fixture()["positions"] if row["body"] == "太阳"]
        natal = next(row["longitude"] for row in rows if row["at_UTC"] == "2000-Jan-01 12:00")
        left = next(row for row in rows if row["at_UTC"] == "2024-Dec-31 13:31")
        right = next(row for row in rows if row["at_UTC"] == "2024-Dec-31 13:32")
        fraction = signed_angle(natal, left["longitude"]) / signed_angle(right["longitude"], left["longitude"])
        reference = _at(left["at_UTC"]) + timedelta(seconds=60 * fraction)
        result = solar_return(BIRTH, 2025, longitude=0, latitude=0)
        actual = actual_utc(result["actual_UTC"]["return_at"])
        self.assertTrue(0 <= fraction <= 1)
        self.assertLess(abs((actual - reference).total_seconds()), 1)

    def test_return_location_changes_houses_not_geocentric_root(self) -> None:
        left = solar_return(BIRTH, 2025, longitude=116.4, latitude=39.9)
        right = solar_return(BIRTH, 2025, longitude=-74, latitude=40.7)
        self.assertEqual(left["root"], right["root"])
        self.assertNotEqual(left["houses"]["cusps"], right["houses"]["cusps"])
        self.assertEqual(left["planets"]["月亮"]["longitude"], right["planets"]["月亮"]["longitude"])
        self.assertTrue(all(1 <= item["house"] <= 12 for item in left["planets"].values()))

    def test_high_latitude_placidus_does_not_switch_houses(self) -> None:
        with self.assertRaisesRegex(ValueError, "Placidus宫制计算失败"):
            solar_return(BIRTH, 2025, longitude=15.6, latitude=78.2)

    def test_return_angles_match_independent_spherical_identities(self) -> None:
        result = solar_return(BIRTH, 2025, longitude=116.4, latitude=39.9)
        engine = Ephemeris()
        jd = result["root"]["return_jd_ut1"]
        epsilon = radians(engine.swe.calc_ut(jd, engine.swe.ECL_NUT)[0][0])
        theta = radians(result["houses"]["armc"])
        latitude = radians(39.9)
        mc = degrees(atan2(sin(theta), cos(theta) * cos(epsilon))) % 360
        asc = (degrees(atan2(-cos(theta), sin(theta) * cos(epsilon) + tan(latitude) * sin(epsilon))) + 180) % 360
        self.assertLess(abs(signed_angle(result["houses"]["midheaven"], mc)), 1e-8)
        self.assertLess(abs(signed_angle(result["houses"]["ascendant"], asc)), 1e-8)

    def test_anniversary_can_cross_utc_year(self) -> None:
        result = solar_return(BIRTH, 2025, longitude=0, latitude=0)
        self.assertTrue(result["root"]["crossed_anniversary_year_boundary"])
        self.assertTrue(result["actual_UTC"]["return_at"].startswith("2024-12-31"))
        self.assertEqual(result["return_year"], 2025)

    def test_leap_day_anniversary_is_explicit_not_an_invalid_date(self) -> None:
        result = solar_return("2000-02-29T12:00:00Z", 2025, longitude=0, latitude=0)
        self.assertTrue(result["root"]["leap_day_anchor_clamped"])
        self.assertTrue(result["root"]["anniversary_anchor_at_UTC"].startswith("2025-02-28"))
        self.assertLess(result["root"]["residual_degrees"], 2e-7)

    def test_birth_year_return_is_birth_instant(self) -> None:
        result = solar_return(BIRTH, 2000, longitude=0, latitude=0)
        engine = Ephemeris()
        self.assertEqual(result["root"]["return_jd_ut1"], engine.julian(actual_utc(BIRTH))[1])

    def test_return_orb_controls_aspects_not_root(self) -> None:
        left = solar_return(BIRTH, 2025, longitude=0, latitude=0, orb=0)
        right = solar_return(BIRTH, 2025, longitude=0, latitude=0, orb=10)
        self.assertEqual(left["root"], right["root"])
        self.assertLessEqual(len(left["aspects"]), len(right["aspects"]))

    def test_invalid_return_parameters_rejected(self) -> None:
        for changes in (
            {"return_year": True},
            {"return_year": 1999},
            {"return_year": 2151},
            {"latitude": 90},
            {"longitude": float("nan")},
            {"orb": float("inf")},
        ):
            args = {"return_year": 2025, "longitude": 0, "latitude": 0} | changes
            with self.assertRaises(ValueError):
                solar_return(BIRTH, **args)

    def test_ut1_not_blind_utc_and_roundtrip(self) -> None:
        engine = Ephemeris()
        moment = actual_utc(BIRTH)
        tt, ut = engine.julian(moment)
        blind = engine.swe.julday(2000, 1, 1, 12)
        self.assertGreater(tt, ut)
        self.assertNotEqual(ut, blind)
        self.assertLess(abs((engine.from_ut(ut) - moment).total_seconds()), 0.001)

    def test_transit_root_residual_after_utc_conversion(self) -> None:
        result = transit_windows(
            {"reference": 0}, "2026-03-18T00:00:00Z", "2026-03-23T00:00:00Z", moving_bodies=("太阳",), orb=1
        )
        row = next(item for item in result["windows"] if item["aspect"] == "合相")
        engine = Ephemeris()
        exact = engine.julian(actual_utc(row["exact_at"][0]))[1]
        error = abs(signed_angle(engine.position("太阳", exact)["longitude"], 0))
        self.assertLess(error, 2e-5)
        self.assertTrue(result["version"].endswith("UTC-UT1"))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AstroNative)
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
    print(json.dumps({"tests": result.testsRun, "successful": result.wasSuccessful(), "skipped": len(result.skipped)}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
