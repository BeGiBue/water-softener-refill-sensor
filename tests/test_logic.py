"""Tests der reinen Logik (ohne Home Assistant). Aufruf: python3 -m unittest discover -s tests -v"""
import importlib.util
import os
import sys
import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_spec = importlib.util.spec_from_file_location(
    "logic", os.path.join(os.path.dirname(__file__), "..", "custom_components", "water_softener_refill_sensor", "logic.py")
)
logic = importlib.util.module_from_spec(_spec)
sys.modules["logic"] = logic  # nötig für dataclasses mit `from __future__ import annotations`
_spec.loader.exec_module(logic)
Settings, SoftenerModel = logic.Settings, logic.SoftenerModel

TZ = ZoneInfo("Europe/Berlin")


def at(day, hh, mm=0, ss=0):
    return datetime(2026, 10, day, hh, mm, ss, tzinfo=TZ)


def model(**kw):
    s = Settings(capacity_kg=kw.pop("capacity_kg", 25.0), per_regen_kg=kw.pop("per_regen_kg", 4.0), **kw)
    return SoftenerModel(s)


def feed(m, readings):
    """readings: Liste (datetime, Zählerstand in L). Der erste Eintrag setzt nur den Bezugswert."""
    events = []
    for i, (when, value) in enumerate(readings):
        events += m.on_meter(value, when, baseline_only=(i == 0))
    return events


class RegenerationDetection(unittest.TestCase):
    def test_night_with_regeneration_is_counted_once(self):
        m = model()
        feed(m, [(at(5, 23), 1000), (at(6, 2, 2), 1010), (at(6, 2, 20), 1040), (at(6, 2, 40), 1070), (at(6, 2, 58), 1085)])
        self.assertEqual(m.state.total_regens, 0)  # erst nach Ende des Fensters
        ev = m.evaluate_pending(at(6, 3, 1, 0), scheduled=True)
        self.assertEqual([e["type"] for e in ev], ["window_closed", "regeneration"])
        self.assertEqual(m.state.total_regens, 1)
        self.assertEqual(m.state.regens_since_refill, 1)
        self.assertAlmostEqual(m.state.stock_kg, 21.0)
        self.assertEqual(m.state.last_regen_at, at(6, 2, 40))  # Zeitpunkt, an dem 45 L überschritten wurden
        # erneute Auswertung zählt nicht doppelt
        self.assertEqual(m.evaluate_pending(at(6, 3, 5), scheduled=True), [])
        self.assertEqual(m.state.total_regens, 1)

    def test_threshold_is_strictly_greater(self):
        m = model()
        feed(m, [(at(6, 1, 59), 1000), (at(6, 2, 30), 1045)])
        m.evaluate_pending(at(6, 3, 1), scheduled=True)
        self.assertEqual(m.state.total_regens, 0)
        m2 = model()
        feed(m2, [(at(6, 1, 59), 1000), (at(6, 2, 30), 1045.1)])
        m2.evaluate_pending(at(6, 3, 1), scheduled=True)
        self.assertEqual(m2.state.total_regens, 1)

    def test_consumption_outside_window_is_ignored(self):
        m = model()
        feed(m, [(at(5, 20), 1000), (at(5, 21), 1200), (at(6, 1, 59), 1210), (at(6, 2, 30), 1220), (at(6, 3, 30), 1500)])
        m.evaluate_pending(at(6, 3, 31), scheduled=True)
        self.assertEqual(m.state.total_regens, 0)
        self.assertAlmostEqual(m.state.window_usage_l, 10.0)

    def test_quiet_night_records_zero(self):
        m = model()
        feed(m, [(at(5, 22), 1000)])
        ev = m.evaluate_pending(at(6, 3, 1), scheduled=True)
        self.assertEqual(ev[0]["usage_l"], 0.0)
        self.assertEqual(m.state.window_usage_l, 0.0)
        self.assertEqual(m.state.total_regens, 0)

    def test_two_nights(self):
        m = model()
        feed(m, [(at(5, 23), 1000), (at(6, 2, 10), 1060)])
        m.evaluate_pending(at(6, 3, 1), scheduled=True)
        m.on_meter(1100, at(6, 18))
        m.on_meter(1110, at(7, 2, 5))
        m.on_meter(1180, at(7, 2, 50))
        m.evaluate_pending(at(7, 3, 1), scheduled=True)
        self.assertEqual(m.state.total_regens, 2)
        self.assertEqual(len(m.state.history), 2)

    def test_meter_reset_is_ignored(self):
        m = model()
        feed(m, [(at(6, 1, 59), 5000), (at(6, 2, 10), 20), (at(6, 2, 20), 40)])
        self.assertAlmostEqual(m.state.window_usage_l, 20.0)  # nur der Zuwachs 20 → 40 zählt

    def test_baseline_only_does_not_count_gap(self):
        m = model()
        feed(m, [(at(5, 22), 1000)])
        # HA war aus; nach dem Neustart um 02:30 liegt der Zähler 300 L höher, soll aber nicht gezählt werden
        m.on_meter(1300, at(6, 2, 30), baseline_only=True)
        m.evaluate_pending(at(6, 3, 1), scheduled=True)
        self.assertEqual(m.state.total_regens, 0)

    def test_catch_up_after_restart(self):
        m = model()
        feed(m, [(at(5, 23), 1000), (at(6, 2, 10), 1080)])
        data = m.to_dict()  # HA wird um 02:30 beendet und erst um 07:00 wieder gestartet
        m2 = SoftenerModel.from_dict(m.settings, data)
        ev = m2.evaluate_pending(at(6, 7), scheduled=False)
        self.assertEqual([e["type"] for e in ev], ["window_closed", "regeneration"])
        self.assertEqual(m2.state.total_regens, 1)

    def test_state_roundtrip(self):
        m = model()
        feed(m, [(at(5, 23), 1000), (at(6, 2, 10), 1060)])
        m.evaluate_pending(at(6, 3, 1), scheduled=True)
        m2 = SoftenerModel.from_dict(m.settings, m.to_dict())
        self.assertEqual(m2.to_dict(), m.to_dict())
        self.assertEqual(m2.state.last_regen_at, m.state.last_regen_at)

    def test_custom_window(self):
        m = model(start_hour=4, end_hour=5, threshold_l=30)
        feed(m, [(at(6, 3, 59), 1000), (at(6, 4, 30), 1031)])
        m.evaluate_pending(at(6, 5, 1), scheduled=True)
        self.assertEqual(m.state.total_regens, 1)


class SaltStock(unittest.TestCase):
    def test_remaining_and_warning(self):
        m = model(capacity_kg=25, per_regen_kg=4, warn_remaining=3)
        self.assertEqual(m.remaining_regens, 6)
        self.assertFalse(m.needs_refill)
        for _ in range(3):
            m.add_manual_regeneration(at(6, 2, 30))
        self.assertAlmostEqual(m.state.stock_kg, 13.0)
        self.assertEqual(m.remaining_regens, 3)
        self.assertTrue(m.needs_refill)  # Restbestand 3 → Warnung
        self.assertAlmostEqual(m.salt_percent, 52.0)

    def test_stock_never_negative(self):
        m = model(capacity_kg=5, per_regen_kg=4)
        m.add_manual_regeneration(at(6, 2), count=3)
        self.assertEqual(m.state.stock_kg, 0.0)
        self.assertEqual(m.remaining_regens, 0)
        self.assertEqual(m.state.total_regens, 3)

    def test_refill_confirms_and_resets(self):
        m = model(capacity_kg=25, per_regen_kg=4)
        m.add_manual_regeneration(at(6, 2), count=5)
        self.assertTrue(m.needs_refill)
        m.refill(at(7, 9), kg=25)
        self.assertEqual(m.state.stock_kg, 25.0)
        self.assertEqual(m.state.regens_since_refill, 0)
        self.assertEqual(m.state.total_regens, 5)  # Gesamtzähler bleibt
        self.assertFalse(m.needs_refill)

    def test_partial_refill_and_clamp(self):
        m = model(capacity_kg=25, per_regen_kg=4)
        m.add_manual_regeneration(at(6, 2), count=5)  # 5 kg übrig
        m.refill(at(7, 9), kg=10)
        self.assertEqual(m.state.stock_kg, 15.0)
        m.refill(at(7, 10), kg=100)
        self.assertEqual(m.state.stock_kg, 25.0)

    def test_refill_requires_positive_amount(self):
        m = model(capacity_kg=25, per_regen_kg=4)
        m.add_manual_regeneration(at(6, 2), count=5)
        for bad in (None, 0, -3):
            with self.assertRaises(ValueError):
                m.refill(at(7, 9), kg=bad)
        self.assertEqual(m.state.stock_kg, 5.0)  # unverändert
        self.assertIsNone(m.state.last_refill_at)

    def test_refill_returns_added_amount(self):
        m = model(capacity_kg=25, per_regen_kg=4)
        m.add_manual_regeneration(at(6, 2), count=5)  # 5 kg übrig
        self.assertEqual(m.refill(at(7, 9), kg=10), 10.0)
        self.assertEqual(m.refill(at(7, 10), kg=100), 10.0)  # nur 10 kg Platz

    def test_small_refill_keeps_warning(self):
        m = model(capacity_kg=25, per_regen_kg=4)
        m.add_manual_regeneration(at(6, 2), count=5)  # 5 kg übrig = 1 Regeneration
        m.refill(at(7, 9), kg=2)  # 7 kg = 1 Regeneration
        self.assertTrue(m.needs_refill)
        m.refill(at(7, 10), kg=10)  # 17 kg = 4 Regenerationen
        self.assertFalse(m.needs_refill)

    def test_counter_resets_only_when_full(self):
        m = model(capacity_kg=25, per_regen_kg=4)
        m.add_manual_regeneration(at(6, 2), count=5)  # 5 kg übrig
        m.refill(at(7, 9), kg=10)  # 15 kg, nicht voll
        self.assertEqual(m.state.regens_since_refill, 5)
        self.assertEqual(m.state.last_refill_at, at(7, 9))
        m.refill(at(7, 10), kg=10)  # 25 kg, voll
        self.assertEqual(m.state.regens_since_refill, 0)

    def test_refill_full_sets_full_and_resets(self):
        m = model(capacity_kg=25, per_regen_kg=4)
        m.add_manual_regeneration(at(6, 2), count=3)  # 13 kg
        self.assertEqual(m.refill_full(at(7, 9)), 12.0)
        self.assertEqual(m.state.stock_kg, 25.0)
        self.assertEqual(m.state.regens_since_refill, 0)
        self.assertEqual(m.state.total_regens, 3)
        self.assertEqual(m.state.last_refill_at, at(7, 9))

    def test_set_regens_since_refill_recalculates_stock(self):
        m = model(capacity_kg=25, per_regen_kg=1.28, warn_remaining=3)
        m.set_regens_since_refill(12)  # 25 - 12 × 1,28 = 9,64 kg → 7 Regenerationen
        self.assertEqual(m.state.regens_since_refill, 12)
        self.assertAlmostEqual(m.state.stock_kg, 9.64)
        self.assertEqual(m.remaining_regens, 7)
        self.assertEqual(m.state.total_regens, 12)  # Gesamtzähler mindestens so groß
        m.set_regens_since_refill(3)
        self.assertEqual(m.state.total_regens, 12)  # wird nicht verkleinert
        self.assertAlmostEqual(m.state.stock_kg, 21.16)

    def test_set_regens_since_refill_limits(self):
        m = model(capacity_kg=25, per_regen_kg=4)
        m.set_regens_since_refill(100)
        self.assertEqual(m.state.stock_kg, 0.0)
        m.set_regens_since_refill(0)
        self.assertEqual(m.state.stock_kg, 25.0)
        with self.assertRaises(ValueError):
            m.set_regens_since_refill(-1)

    def test_initial_stock_and_set_stock(self):
        s = Settings(capacity_kg=25, per_regen_kg=4)
        m = SoftenerModel(s, initial_stock_kg=12)
        self.assertEqual(m.state.stock_kg, 12.0)
        m.set_stock(40)
        self.assertEqual(m.state.stock_kg, 25.0)

    def test_capacity_reduced_clamps_stock(self):
        s = Settings(capacity_kg=25, per_regen_kg=4)
        m = SoftenerModel(s)
        m2 = SoftenerModel.from_dict(Settings(capacity_kg=20, per_regen_kg=4), m.to_dict())
        self.assertEqual(m2.state.stock_kg, 20.0)

    def test_regeneration_reduces_stock_via_detection(self):
        m = model(capacity_kg=25, per_regen_kg=4, warn_remaining=3)
        day = 6
        for n in range(4):  # vier Nächte mit Regeneration → 25 - 16 = 9 kg → Restbestand 2
            feed_start = 1000 + n * 200
            m.on_meter(feed_start, at(day + n - 1, 23))
            m.on_meter(feed_start + 80, at(day + n, 2, 30))
            m.evaluate_pending(at(day + n, 3, 1), scheduled=True)
        self.assertEqual(m.state.total_regens, 4)
        self.assertAlmostEqual(m.state.stock_kg, 9.0)
        self.assertEqual(m.remaining_regens, 2)
        self.assertTrue(m.needs_refill)


class HygieneRule(unittest.TestCase):
    """Die Anlage regeneriert spätestens 7 Tage nach der letzten Regeneration."""

    def test_no_regeneration_yet(self):
        m = model()
        self.assertIsNone(m.next_regen_due(TZ))
        self.assertFalse(m.regen_overdue(at(20, 12)))

    def test_next_due_is_window_start_seven_days_later(self):
        m = model(capacity_kg=100)
        m.add_manual_regeneration(at(6, 2, 40))
        self.assertEqual(m.next_regen_due(TZ), at(13, 2))

    def test_overdue_after_window_of_due_day(self):
        m = model(capacity_kg=100)
        m.add_manual_regeneration(at(6, 2, 40))
        self.assertFalse(m.regen_overdue(at(13, 1, 0)))  # vor dem Fenster
        self.assertFalse(m.regen_overdue(at(13, 2, 30)))  # im Fenster
        self.assertFalse(m.regen_overdue(at(13, 3, 0, 59)))  # Auswertung noch nicht erfolgt
        self.assertTrue(m.regen_overdue(at(13, 3, 1)))
        self.assertTrue(m.regen_overdue(at(15, 12)))

    def test_regeneration_on_due_day_clears_overdue(self):
        m = model(capacity_kg=100)
        m.add_manual_regeneration(at(6, 2, 40))
        feed(m, [(at(12, 23), 1000), (at(13, 2, 10), 1020), (at(13, 2, 50), 1060)])
        events = m.evaluate_pending(at(13, 3, 1), scheduled=True)
        self.assertTrue(any(e["type"] == "regeneration" for e in events))
        self.assertFalse(m.regen_overdue(at(13, 3, 1)))
        self.assertEqual(m.next_regen_due(TZ), at(20, 2))

    def test_set_last_regeneration_moves_due_date(self):
        m = model(capacity_kg=100)
        m.set_last_regeneration(at(2, 2, 30), now=at(6, 12))
        self.assertEqual(m.state.last_regen_at, at(2, 2, 30))
        self.assertEqual(m.next_regen_due(TZ), at(9, 2))
        self.assertFalse(m.regen_overdue(at(6, 12)))
        self.assertEqual(m.state.total_regens, 0)  # nur das Datum, keine zusätzliche Regeneration
        with self.assertRaises(ValueError):
            m.set_last_regeneration(at(7, 2), now=at(6, 12))  # Zukunft
        self.assertEqual(m.state.last_regen_at, at(2, 2, 30))

    def test_typical_regeneration_volume_is_detected(self):
        """Die Anlage verbraucht meist 52–53 Liter: deutlich über dem Standard-Schwellwert von 45 Litern."""
        for liters in (52, 53):
            m = model(capacity_kg=100)
            feed(m, [(at(5, 23), 1000), (at(6, 2, 10), 1000 + liters / 2), (at(6, 2, 50), 1000 + liters)])
            m.evaluate_pending(at(6, 3, 1), scheduled=True)
            self.assertEqual(m.state.total_regens, 1)


UTC = ZoneInfo("UTC")


def berlin(y, mo, d, hh, mm=0, ss=0, fold=0):
    return datetime(y, mo, d, hh, mm, ss, fold=fold, tzinfo=TZ)


class DaylightSaving(unittest.TestCase):
    """Fenster in echter Zeit (UTC): Die Anlage folgt der Ortszeit und stellt selbst um (Annahme, siehe logic.py)."""

    def test_october_night_counts_first_hour_only(self):
        m = model(capacity_kg=100)
        day = date(2026, 10, 25)
        # 02:00 MESZ (00:00 UTC) bis 02:00 MEZ (01:00 UTC), Auswertung 02:01 MEZ
        self.assertEqual(m.window_start(day, TZ).astimezone(UTC), datetime(2026, 10, 25, 0, 0, tzinfo=UTC))
        self.assertEqual(m.window_end(day, TZ).astimezone(UTC), datetime(2026, 10, 25, 1, 1, tzinfo=UTC))
        ev = feed(m, [(berlin(2026, 10, 25, 1, 30), 1000), (berlin(2026, 10, 25, 2, 30), 1025),
                      (berlin(2026, 10, 25, 2, 30, fold=1), 1050)])  # zweite 02:30 (MEZ) liegt nach dem Fenster
        self.assertEqual(ev, [{"type": "window_closed", "date": day, "usage_l": 25.0}])
        self.assertEqual(m.state.total_regens, 0)

    def test_october_night_not_evaluated_too_early(self):
        m = model(capacity_kg=100)
        feed(m, [(berlin(2026, 10, 25, 1, 30), 1000), (berlin(2026, 10, 25, 2, 30), 1052)])
        # 03:01 MESZ gibt es nicht; 02:01 MESZ (erste Stunde) ist noch im Fenster
        self.assertEqual(m.evaluate_pending(berlin(2026, 10, 25, 2, 1), scheduled=True), [])
        ev = m.evaluate_pending(berlin(2026, 10, 25, 2, 1, fold=1), scheduled=True)
        self.assertEqual([e["type"] for e in ev], ["window_closed", "regeneration"])

    def test_march_night_window_is_three_to_four(self):
        m = model(capacity_kg=100)
        day = date(2027, 3, 28)
        self.assertEqual(m.window_start(day, TZ), berlin(2027, 3, 28, 3))
        self.assertEqual(m.window_end(day, TZ), berlin(2027, 3, 28, 4, 1))
        feed(m, [(berlin(2027, 3, 28, 1, 59), 1000), (berlin(2027, 3, 28, 3, 10), 1020),
                 (berlin(2027, 3, 28, 3, 40), 1052)])
        self.assertEqual(m.evaluate_pending(berlin(2027, 3, 28, 3, 1), scheduled=True), [])  # zu früh
        ev = m.evaluate_pending(berlin(2027, 3, 28, 4, 1), scheduled=True)
        self.assertEqual([e["type"] for e in ev], ["window_closed", "regeneration"])
        self.assertEqual(m.state.last_regen_at, berlin(2027, 3, 28, 3, 40))

    def test_march_due_date_and_overdue(self):
        m = model(capacity_kg=100)
        m.add_manual_regeneration(berlin(2027, 3, 21, 2, 30))
        self.assertEqual(m.next_regen_due(TZ), berlin(2027, 3, 28, 3))
        self.assertFalse(m.regen_overdue(berlin(2027, 3, 28, 3, 30)))
        self.assertFalse(m.regen_overdue(berlin(2027, 3, 28, 4, 0, 59)))
        self.assertTrue(m.regen_overdue(berlin(2027, 3, 28, 4, 1)))

    def test_normal_night_unchanged(self):
        m = model()
        day = date(2026, 10, 6)
        self.assertEqual(m.window_start(day, TZ), at(6, 2))
        self.assertEqual(m.window_end(day, TZ), at(6, 3, 1))


class WindowBoundaries(unittest.TestCase):
    """Erfasst wird von Fensterbeginn bis Fensterende + 1 Minute (verspätete Zählerwerte, siehe logic.py)."""

    def test_boundaries(self):
        m = model(capacity_kg=100)
        feed(m, [(at(6, 1), 1000),
                 (at(6, 1, 59, 59), 1010),  # vor dem Fenster
                 (at(6, 2, 0, 0), 1020),    # Beginn: zählt
                 (at(6, 3, 0, 30), 1060),   # Nachlauf: zählt
                 (at(6, 3, 1, 0), 1160)])   # Auswertezeitpunkt: zählt nicht mehr
        self.assertEqual(m.state.window_usage_l, 50.0)
        self.assertEqual(m.state.total_regens, 1)
        self.assertEqual(m.state.evaluated_date, date(2026, 10, 6))
        self.assertEqual(m.state.last_regen_at, at(6, 3, 0, 30))


class RegensSinceRefillRelative(unittest.TestCase):
    """set_regens_since_refill ändert den Bestand relativ zur bisherigen Anzahl."""

    def test_partial_refill_is_kept(self):
        m = model(capacity_kg=25, per_regen_kg=1.28)
        m.set_regens_since_refill(16)
        self.assertAlmostEqual(m.state.stock_kg, 4.52)
        m.refill(at(7, 9), 20)
        self.assertAlmostEqual(m.state.stock_kg, 24.52)
        self.assertEqual(m.state.regens_since_refill, 16)
        m.set_regens_since_refill(16)  # gleicher Wert: keine Änderung
        self.assertAlmostEqual(m.state.stock_kg, 24.52)
        m.set_regens_since_refill(15)  # eine weniger: +1,28 kg, begrenzt auf 25 kg
        self.assertAlmostEqual(m.state.stock_kg, 25.0)
        self.assertEqual(m.state.total_regens, 16)

    def test_fresh_setup(self):
        m = SoftenerModel(Settings(capacity_kg=25, per_regen_kg=1.28), initial_stock_kg=25)
        m.set_regens_since_refill(16)
        self.assertAlmostEqual(m.state.stock_kg, 4.52)

    def test_set_stock_keeps_counter(self):
        m = model(capacity_kg=25, per_regen_kg=1.28)
        m.set_regens_since_refill(5)
        m.set_stock(25)
        self.assertEqual(m.state.regens_since_refill, 5)


class ManualRegenerationTime(unittest.TestCase):
    def test_older_regeneration_does_not_move_last_back(self):
        m = model(capacity_kg=100)
        m.add_manual_regeneration(at(6, 2, 30))
        m.add_manual_regeneration(at(3, 2, 30))  # später nachgetragen, liegt aber davor
        self.assertEqual(m.state.last_regen_at, at(6, 2, 30))
        self.assertEqual(m.state.history, [at(6, 2, 30), at(3, 2, 30)])
        self.assertEqual(m.state.total_regens, 2)


class StoredStateCompatibility(unittest.TestCase):
    def test_empty_and_partial_dicts(self):
        s = Settings(capacity_kg=25, per_regen_kg=4)
        m = SoftenerModel.from_dict(s, {})
        self.assertEqual(m.state.stock_kg, 25.0)
        m = SoftenerModel.from_dict(s, {"stock_kg": 10, "total_regens": 2})  # Stand ohne spätere Felder
        self.assertEqual((m.state.stock_kg, m.state.total_regens, m.state.history), (10.0, 2, []))

    def test_strings_and_garbage(self):
        s = Settings(capacity_kg=25, per_regen_kg=4)
        m = SoftenerModel.from_dict(s, {
            "stock_kg": "12.5", "total_regens": "3", "regens_since_refill": None, "last_value_l": "1000",
            "window_usage_l": "7", "window_date": "kaputt", "last_regen_at": "2026-10-01T02:30:00+02:00",
            "history": [None, "2026-10-01T02:30:00+02:00", "unsinn"],
        })
        self.assertEqual(m.state.stock_kg, 12.5)
        self.assertEqual(m.state.total_regens, 3)
        self.assertEqual(m.state.regens_since_refill, 0)
        self.assertEqual(m.state.last_value_l, 1000.0)
        self.assertIsNone(m.state.window_date)
        self.assertEqual(len(m.state.history), 1)
        m.on_meter(1010, at(6, 2, 10))  # darf nicht mit TypeError abbrechen
        self.assertEqual(m.state.window_usage_l, 10.0)


if __name__ == "__main__":
    unittest.main()
