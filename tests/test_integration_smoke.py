"""Ablauftest der Home-Assistant-Anbindung mit Attrappen (siehe ha_stubs.py).

Spielt eine Nacht durch: Zählerstände -> Regeneration erkannt -> Salzbestand -> Meldung -> Bestätigung.
"""
import asyncio
import os
import sys
import types
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ha_stubs  # noqa: E402

ha_stubs.install()
from ha_stubs import TZ, FakeDt, FakeNotifications, FakeStore  # noqa: E402

from custom_components.water_softener_refill_sensor import (  # noqa: E402
    _manager_for,
    async_remove_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.water_softener_refill_sensor import binary_sensor as bs_mod  # noqa: E402
from custom_components.water_softener_refill_sensor import button as btn_mod  # noqa: E402
from custom_components.water_softener_refill_sensor import config_flow  # noqa: E402
from custom_components.water_softener_refill_sensor import datetime as dt_mod  # noqa: E402
from custom_components.water_softener_refill_sensor import number as num_mod  # noqa: E402
from custom_components.water_softener_refill_sensor import sensor as sensor_mod  # noqa: E402
from custom_components.water_softener_refill_sensor.manager import SoftenerManager  # noqa: E402


def local(day, hh, mm=0):
    return datetime(2026, 10, day, hh, mm, tzinfo=TZ)


class FakeState:
    def __init__(self, state, unit="L", when=None):
        self.state = state
        self.attributes = {"unit_of_measurement": unit} if unit else {}
        self.last_updated = when or FakeDt._now


class FakeStates:
    def __init__(self):
        self._s = {}

    def get(self, entity_id):
        return self._s.get(entity_id)

    def set(self, entity_id, state):
        self._s[entity_id] = state


class FakeHass:
    def __init__(self):
        self.data = {}
        self.config = types.SimpleNamespace(language="de")
        self.states = FakeStates()
        self.state_cbs = []
        self.timers = []  # (Zeitpunkt UTC, Aktion) aus async_track_point_in_utc_time
        self.services = types.SimpleNamespace(registered={}, async_register=self._register)
        calls = []
        self.calls = calls

        async def forward(entry, platforms):
            calls.append(("forward", list(platforms)))

        async def unload(entry, platforms):
            return True

        async def reload(entry_id):
            calls.append(("reload", entry_id))

        self.config_entries = types.SimpleNamespace(
            async_forward_entry_setups=forward, async_unload_platforms=unload, async_reload=reload
        )

    def _register(self, domain, name, handler, schema=None):
        self.services.registered[name] = handler


class FakeEntry:
    def __init__(self, **data):
        self.entry_id = "abc123"
        self.title = "Enthärtungsanlage"
        self.data = {
            "name": "Enthärtungsanlage",
            "water_entity": "sensor.wasser_total",
            "capacity_kg": 17.0,
            "per_regen_kg": 4.0,
            "threshold_l": 45,
            "window_start_hour": 2,
            "window_end_hour": 3,
            "warn_remaining": 3,
        }
        self.data.update(data)
        self.options = {}

    def add_update_listener(self, fn):
        return lambda: None

    def async_on_unload(self, fn):
        pass


def push(hass, value, when, unit="L"):
    """Zählerstand setzen und das Ereignis an den Manager schicken."""
    FakeDt._now = when
    state = FakeState(str(value), unit, when)
    hass.states.set("sensor.wasser_total", state)
    for cb in hass.state_cbs:
        cb(types.SimpleNamespace(data={"new_state": state}))


def window_end(hass, when):
    """Uhr auf when stellen und alle bis dahin fälligen Zeitpläne auslösen (wie Home Assistant)."""
    FakeDt._now = when
    while True:
        due = sorted((t for t in hass.timers if t[0] <= when), key=lambda t: t[0])
        if not due:
            return
        hass.timers.remove(due[0])
        due[0][1](due[0][0])


class NightScenario(unittest.TestCase):
    def setUp(self):
        FakeStore.DATA.clear()
        FakeNotifications.active.clear()
        FakeNotifications.log.clear()

    def start(self, **entry_kw):
        hass = FakeHass()
        entry = FakeEntry(**entry_kw)
        FakeDt._now = local(5, 22)
        hass.states.set("sensor.wasser_total", FakeState("1000", "L", local(5, 21)))
        return hass, entry

    def test_full_night_with_low_salt_notification_and_confirmation(self):
        hass, entry = self.start()  # Kapazität 17 kg, 4 kg je Regeneration → Restbestand 4, Warnung ab 3
        asyncio.run(self._night(hass, entry))

    async def _night(self, hass, entry):
        await async_setup(hass, {})
        await async_setup_entry(hass, entry)
        mgr = hass.data["water_softener_refill_sensor"]["abc123"]
        self.assertEqual(mgr.coordinator.data["regenerations_left"], 4)
        self.assertEqual(FakeNotifications.active, {})  # noch keine Meldung
        # Zeitplan: Auswertung um 03:01:00 Ortszeit, als Zeitpunkt in UTC
        self.assertEqual([t[0] for t in hass.timers], [local(6, 3, 1).astimezone(ZoneInfo("UTC"))])

        for when, value in [(local(6, 2, 5), 1010), (local(6, 2, 20), 1040), (local(6, 2, 40), 1070), (local(6, 2, 58), 1085)]:
            push(hass, value, when)
        self.assertEqual(mgr.coordinator.data["total_regenerations"], 0)
        self.assertEqual(mgr.coordinator.data["window_usage_l"], 85.0)
        window_end(hass, local(6, 3, 1))

        d = mgr.coordinator.data
        self.assertEqual(d["total_regenerations"], 1)
        self.assertEqual(d["salt_stock_kg"], 13.0)
        self.assertEqual(d["regenerations_left"], 3)
        self.assertTrue(d["refill_needed"])
        note = FakeNotifications.active["water_softener_refill_sensor_abc123_low_salt"]
        self.assertIn("3 Regenerationen", note["message"])
        self.assertIn("13.0 kg von 17.0 kg", note["message"])

        # Sensoren und Binärsensor lesen die Werte
        values = {}
        for desc in sensor_mod.SENSORS:
            ent = sensor_mod.EnthaertungSensor(mgr.coordinator, entry, desc)
            values[desc.key] = ent.native_value
        self.assertEqual(values["total_regenerations"], 1)
        self.assertEqual(values["salt_stock"], 13.0)
        self.assertEqual(values["salt_level"], 76.5)
        self.assertEqual(values["regenerations_left"], 3)
        self.assertEqual(values["last_regeneration"], local(6, 2, 40))
        self.assertEqual(values["window_usage"], 85.0)
        self.assertEqual(values["next_regeneration_due"], local(13, 2))
        flag = bs_mod.RefillNeededBinarySensor(mgr.coordinator, entry)
        self.assertTrue(flag.is_on)

        # Meldung bleibt bestehen, bis eine Nachfüllmenge bestätigt wird (hier: Eingabe + Taste)
        button = btn_mod.ConfirmRefillButton(mgr, entry)
        amount = num_mod.RefillAmountNumber(mgr, entry)
        self.assertEqual(amount.native_value, 0.0)
        self.assertEqual(amount.native_max_value, 17.0)
        with self.assertRaises(Exception):  # ohne Menge keine Quittierung
            await button.async_press()
        self.assertIn("water_softener_refill_sensor_abc123_low_salt", FakeNotifications.active)
        await amount.async_set_native_value(2.0)  # 2 kg: 13 + 2 = 15 kg = 3 Regenerationen → weiter Warnung
        self.assertEqual(amount.native_value, 2.0)
        await button.async_press()
        self.assertEqual(mgr.coordinator.data["salt_stock_kg"], 15.0)
        self.assertIn("water_softener_refill_sensor_abc123_low_salt", FakeNotifications.active)
        self.assertTrue(flag.is_on)
        self.assertEqual(amount.native_value, 0.0)  # Eingabe nach dem Bestätigen zurückgesetzt
        self.assertEqual(mgr.coordinator.data["regenerations_since_refill"], 1)  # nicht voll: Zähler bleibt
        await amount.async_set_native_value(4.0)  # 15 + 4 → begrenzt auf 17 kg
        await button.async_press()
        self.assertEqual(FakeNotifications.active, {})
        self.assertFalse(flag.is_on)
        self.assertEqual(mgr.coordinator.data["salt_stock_kg"], 17.0)
        self.assertEqual(mgr.coordinator.data["regenerations_since_refill"], 0)
        self.assertEqual(mgr.coordinator.data["total_regenerations"], 1)

        # Zustand wurde gespeichert
        self.assertIn("water_softener_refill_sensor.abc123", FakeStore.DATA)
        await async_unload_entry(hass, entry)
        await async_remove_entry(hass, entry)
        self.assertNotIn("water_softener_refill_sensor.abc123", FakeStore.DATA)

    def test_overdue_notification(self):
        hass, entry = self.start(capacity_kg=100.0)
        asyncio.run(self._overdue(hass, entry))

    async def _overdue(self, hass, entry):
        await async_setup(hass, {})
        await async_setup_entry(hass, entry)
        mgr = hass.data["water_softener_refill_sensor"]["abc123"]
        key = "water_softener_refill_sensor_abc123_overdue"
        push(hass, 1090, local(6, 2, 30))  # Regeneration am 6.
        window_end(hass, local(6, 3, 1))
        self.assertEqual(mgr.coordinator.data["total_regenerations"], 1)
        self.assertFalse(mgr.coordinator.data["regeneration_overdue"])
        self.assertEqual(mgr.coordinator.data["next_regeneration_due"], local(13, 2))
        flag = bs_mod.RegenerationOverdueBinarySensor(mgr.coordinator, entry)
        # Am 13. kommt keine Regeneration: nach der Auswertung Meldung
        window_end(hass, local(13, 3, 1))
        self.assertTrue(mgr.coordinator.data["regeneration_overdue"])
        self.assertTrue(flag.is_on)
        self.assertIn(key, FakeNotifications.active)
        self.assertIn("06.10.2026 02:30", FakeNotifications.active[key]["message"])
        # Regeneration von Hand nachgetragen: Meldung verschwindet
        FakeDt._now = local(13, 8)
        await mgr.async_add_regeneration(1)
        self.assertFalse(mgr.coordinator.data["regeneration_overdue"])
        self.assertNotIn(key, FakeNotifications.active)

    def test_full_button(self):
        hass, entry = self.start()
        asyncio.run(self._full(hass, entry))

    async def _full(self, hass, entry):
        await async_setup(hass, {})
        await async_setup_entry(hass, entry)
        mgr = hass.data["water_softener_refill_sensor"]["abc123"]
        await mgr.async_add_regeneration(2)  # 17 - 8 = 9 kg → Meldung
        self.assertIn("water_softener_refill_sensor_abc123_low_salt", FakeNotifications.active)
        amount = num_mod.RefillAmountNumber(mgr, entry)
        await amount.async_set_native_value(3.0)
        full = btn_mod.ConfirmFullButton(mgr, entry)
        await full.async_press()  # ohne Mengeneingabe
        d = mgr.coordinator.data
        self.assertEqual(d["salt_stock_kg"], 17.0)
        self.assertEqual(d["regenerations_since_refill"], 0)
        self.assertEqual(d["total_regenerations"], 2)
        self.assertEqual(d["refill_input_kg"], 0.0)
        self.assertIsNotNone(d["last_refill"])
        self.assertEqual(FakeNotifications.active, {})

    def test_cubic_meter_unit_and_unavailable_baseline(self):
        hass, entry = self.start(capacity_kg=100.0)
        asyncio.run(self._cubic(hass, entry))

    async def _cubic(self, hass, entry):
        hass.states.set("sensor.wasser_total", FakeState("1.000", "m³", local(5, 21)))
        await async_setup_entry(hass, entry)
        mgr = hass.data["water_softener_refill_sensor"]["abc123"]
        push(hass, 1.010, local(6, 2, 10), unit="m³")  # +10 L
        push(hass, "unavailable", local(6, 2, 20), unit="m³")  # Zähler fällt aus
        push(hass, 1.300, local(6, 2, 30), unit="m³")  # +290 L, aber nach Ausfall nur Bezugswert
        push(hass, 1.346, local(6, 2, 50), unit="m³")  # +46 L
        window_end(hass, local(6, 3, 1))
        self.assertEqual(mgr.coordinator.data["window_usage_l"], 56.0)
        self.assertEqual(mgr.coordinator.data["total_regenerations"], 1)
        self.assertEqual(FakeNotifications.active, {})  # Kapazität 100 kg → kein Salzmangel

    def test_catch_up_after_restart(self):
        hass, entry = self.start(capacity_kg=100.0)
        asyncio.run(self._restart(hass, entry))

    async def _restart(self, hass, entry):
        await async_setup_entry(hass, entry)
        push(hass, 1090, local(6, 2, 30))  # +90 L im Fenster
        # HA wird beendet (Zustand gespeichert) und erst um 07:00 neu gestartet
        mgr = hass.data["water_softener_refill_sensor"]["abc123"]
        await mgr.async_stop()
        hass2 = FakeHass()
        hass2.states.set("sensor.wasser_total", FakeState("1090", "L", local(6, 7)))
        FakeDt._now = local(6, 7)
        await async_setup_entry(hass2, entry)
        d = hass2.data["water_softener_refill_sensor"]["abc123"].coordinator.data
        self.assertEqual(d["total_regenerations"], 1)
        self.assertEqual(d["salt_stock_kg"], 96.0)

    def test_services(self):
        hass, entry = self.start()
        asyncio.run(self._services(hass, entry))

    async def _services(self, hass, entry):
        await async_setup(hass, {})
        await async_setup_entry(hass, entry)
        mgr = hass.data["water_softener_refill_sensor"]["abc123"]
        call = lambda **data: types.SimpleNamespace(data=data)  # noqa: E731
        reg = hass.services.registered
        await reg["add_regeneration"](call(count=2))
        self.assertEqual(mgr.coordinator.data["total_regenerations"], 2)
        self.assertEqual(mgr.coordinator.data["salt_stock_kg"], 9.0)
        self.assertTrue(mgr.coordinator.data["refill_needed"])
        self.assertIn("water_softener_refill_sensor_abc123_low_salt", FakeNotifications.active)
        await reg["set_salt_stock"](call(kg=16.0))
        self.assertEqual(mgr.coordinator.data["regenerations_left"], 4)
        self.assertEqual(FakeNotifications.active, {})
        for bad in (None, 0):
            with self.assertRaises(Exception):  # Menge ist Pflicht
                await reg["refill"](call(kg=bad))
        self.assertEqual(mgr.coordinator.data["salt_stock_kg"], 16.0)
        await reg["refill"](call(kg=5.0))
        self.assertEqual(mgr.coordinator.data["salt_stock_kg"], 17.0)
        # falscher Eintrag
        with self.assertRaises(Exception):
            _manager_for(hass, call(config_entry="gibt-es-nicht"))

    def test_correct_last_regeneration_and_count(self):
        hass, entry = self.start()  # 17 kg, 4 kg je Regeneration
        asyncio.run(self._corrections(hass, entry))

    async def _corrections(self, hass, entry):
        await async_setup(hass, {})
        await async_setup_entry(hass, entry)
        mgr = hass.data["water_softener_refill_sensor"]["abc123"]
        FakeDt._now = local(13, 12)
        # Datum der letzten Regeneration (Eingabe-Entität, UTC wie aus der Oberfläche)
        last = dt_mod.LastRegenerationDateTime(mgr, entry)
        self.assertIsNone(last.native_value)
        await last.async_set_value(datetime(2026, 10, 5, 0, 30, tzinfo=ZoneInfo("UTC")))  # = 02:30 Ortszeit
        d = mgr.coordinator.data
        self.assertEqual(d["last_regeneration"], local(5, 2, 30))
        self.assertEqual(d["next_regeneration_due"], local(12, 2))
        self.assertTrue(d["regeneration_overdue"])  # 12. ist vorbei, keine Regeneration erkannt
        self.assertIn("water_softener_refill_sensor_abc123_overdue", FakeNotifications.active)
        self.assertEqual(d["total_regenerations"], 0)  # Datum allein zählt keine Regeneration
        with self.assertRaises(Exception):  # Zukunft
            await last.async_set_value(local(20, 2))
        # Dienst mit Ortszeit ohne Zeitzone: Meldung verschwindet
        await hass.services.registered["set_last_regeneration"](
            types.SimpleNamespace(data={"datetime": datetime(2026, 10, 12, 2, 40)})
        )
        self.assertEqual(mgr.coordinator.data["last_regeneration"], local(12, 2, 40))
        self.assertNotIn("water_softener_refill_sensor_abc123_overdue", FakeNotifications.active)

        # Bekannte Regenerationen seit dem Nachfüllen: Bestand 17 - 3 × 4 = 5 kg → Restbestand 1 → Meldung
        count = num_mod.RegenerationsSinceRefillNumber(mgr, entry)
        self.assertEqual(count.native_value, 0.0)
        await count.async_set_native_value(3.0)
        d = mgr.coordinator.data
        self.assertEqual(count.native_value, 3.0)
        self.assertEqual(d["salt_stock_kg"], 5.0)
        self.assertEqual(d["regenerations_left"], 1)
        self.assertIn("water_softener_refill_sensor_abc123_low_salt", FakeNotifications.active)
        await hass.services.registered["set_regenerations_since_refill"](types.SimpleNamespace(data={"count": 1}))
        self.assertEqual(mgr.coordinator.data["salt_stock_kg"], 13.0)
        self.assertEqual(mgr.coordinator.data["total_regenerations"], 3)
        self.assertIn("water_softener_refill_sensor_abc123_low_salt", FakeNotifications.active)  # 3 = Warnschwelle
        await count.async_set_native_value(0.0)  # 17 kg = 4 Regenerationen → keine Meldung
        self.assertEqual(mgr.coordinator.data["salt_stock_kg"], 17.0)
        self.assertEqual(FakeNotifications.active, {})

    def test_english_notification(self):
        hass, entry = self.start(capacity_kg=8.0)  # Restbestand 2 → sofort Meldung
        hass.config.language = "en"
        asyncio.run(async_setup_entry(hass, entry))
        note = FakeNotifications.active["water_softener_refill_sensor_abc123_low_salt"]
        self.assertEqual(note["title"], "Refill salt")
        self.assertIn("2 more regenerations", note["message"])


class ReviewFixes(unittest.TestCase):
    """Befunde aus dem Review 1.2.0 (Ablauf mit Attrappen; echte HA-Prüfung in tests_ha/)."""

    def setUp(self):
        FakeStore.DATA.clear()
        FakeNotifications.active.clear()
        FakeNotifications.log.clear()
        self.hass = FakeHass()
        self.entry = FakeEntry(capacity_kg=100.0)
        FakeDt._now = local(5, 22)
        self.hass.states.set("sensor.wasser_total", FakeState("1000", "L", local(5, 21)))

    def run_async(self, coro):
        return asyncio.run(coro)

    async def _setup(self):
        await async_setup(self.hass, {})
        await async_setup_entry(self.hass, self.entry)
        return self.hass.data["water_softener_refill_sensor"]["abc123"]

    def test_overdue_text_names_due_day(self):  # N1
        async def run():
            mgr = await self._setup()
            await mgr.async_set_last_regeneration(local(5, 2, 30))
            window_end(self.hass, local(12, 3, 1))
            msg = FakeNotifications.active["water_softener_refill_sensor_abc123_overdue"]["message"]
            self.assertIn("am Fälligkeitstag (12.10.2026)", msg)
            self.assertNotIn("mehr als 7 Tagen", msg)
        self.run_async(run())

    def test_add_regeneration_with_datetime(self):  # N1
        async def run():
            mgr = await self._setup()
            FakeDt._now = local(9, 15)
            reg = self.hass.services.registered["add_regeneration"]
            await reg(types.SimpleNamespace(data={"count": 1, "datetime": datetime(2026, 10, 7, 2, 30)}))
            self.assertEqual(mgr.coordinator.data["last_regeneration"], local(7, 2, 30))
            self.assertEqual(mgr.coordinator.data["next_regeneration_due"], local(14, 2))
            await reg(types.SimpleNamespace(data={"count": 1}))  # ohne Zeitpunkt: jetzt
            self.assertEqual(mgr.coordinator.data["last_regeneration"], local(9, 15))
            with self.assertRaises(ha_stubs.ServiceValidationError) as ctx:
                await reg(types.SimpleNamespace(data={"count": 1, "datetime": datetime(2026, 10, 10, 2, 30)}))
            self.assertEqual(ctx.exception.translation_key, "datetime_in_future")
            self.assertEqual(mgr.coordinator.data["total_regenerations"], 2)
        self.run_async(run())

    def test_unload_dismisses_and_reload_recreates(self):  # N3
        async def run():
            mgr = await self._setup()
            await mgr.async_set_stock(1.0)
            key = "water_softener_refill_sensor_abc123_low_salt"
            self.assertIn(key, FakeNotifications.active)
            await async_unload_entry(self.hass, self.entry)
            self.assertNotIn(key, FakeNotifications.active)
            self.assertEqual(self.hass.timers, [])  # Zeitplan abgemeldet
            await async_setup_entry(self.hass, self.entry)
            self.assertIn(key, FakeNotifications.active)
        self.run_async(run())

    def test_errors_are_translated(self):  # N4
        async def run():
            mgr = await self._setup()
            call = lambda **data: types.SimpleNamespace(data=data)  # noqa: E731
            cases = [
                (mgr.async_refill(0), "refill_amount_required"),
                (mgr.async_set_last_regeneration(local(20, 2)), "datetime_in_future"),
                (mgr.async_set_regens_since_refill(-1), "negative_count"),
            ]
            for coro, key in cases:
                with self.assertRaises(ha_stubs.ServiceValidationError) as ctx:
                    await coro
                self.assertEqual((ctx.exception.translation_domain, ctx.exception.translation_key),
                                 ("water_softener_refill_sensor", key))
            with self.assertRaises(ha_stubs.ServiceValidationError) as ctx:
                _manager_for(self.hass, call(config_entry="gibt-es-nicht"))
            self.assertEqual(ctx.exception.translation_key, "unknown_entry")
            self.assertEqual(ctx.exception.translation_placeholders, {"entry_id": "gibt-es-nicht"})
        self.run_async(run())

    def test_two_entries_need_config_entry(self):
        async def run():
            mgr = await self._setup()
            second = FakeEntry()
            second.entry_id = "xyz789"
            await async_setup_entry(self.hass, second)
            call = lambda **data: types.SimpleNamespace(data=data)  # noqa: E731
            with self.assertRaises(ha_stubs.ServiceValidationError) as ctx:
                _manager_for(self.hass, call())
            self.assertEqual(ctx.exception.translation_key, "multiple_entries")
            self.assertIs(_manager_for(self.hass, call(config_entry="abc123")), mgr)
            await self.hass.services.registered["add_regeneration"](call(config_entry="xyz789", count=1))
            self.assertEqual(mgr.coordinator.data["total_regenerations"], 0)
            self.assertEqual(self.hass.data["water_softener_refill_sensor"]["xyz789"].model.state.total_regens, 1)
        self.run_async(run())

    def test_unknown_unit_is_not_counted(self):  # M3
        async def run():
            mgr = await self._setup()
            key = "water_softener_refill_sensor_abc123_unit"
            push(self.hass, 1010, local(6, 2, 5))
            push(self.hass, 2000, local(6, 2, 10), unit="Kubikliter")
            self.assertIn(key, FakeNotifications.active)
            self.assertIn("Kubikliter", FakeNotifications.active[key]["message"])
            self.assertEqual(FakeNotifications.active[key]["title"], "Einheit des Wasserzählers unbekannt")
            push(self.hass, 2100, local(6, 2, 20), unit=None)  # fehlende Einheit: ebenfalls nicht zählen
            push(self.hass, 2200, local(6, 2, 30), unit="L")  # bekannte Einheit: nur Bezugswert, Meldung weg
            self.assertNotIn(key, FakeNotifications.active)
            push(self.hass, 2250, local(6, 2, 40), unit="L")
            self.assertEqual(mgr.coordinator.data["window_usage_l"], 60.0)  # 10 + 50
        self.run_async(run())

    def test_unit_change_sets_baseline_and_gallons_count(self):  # M3
        async def run():
            mgr = await self._setup()
            push(self.hass, 1010, local(6, 2, 5))  # +10 L
            push(self.hass, 300.0, local(6, 2, 10), unit="gal")  # Wechsel: nur Bezugswert
            push(self.hass, 314.0, local(6, 2, 30), unit="gal")  # +14 gal ≈ 53 L
            self.assertAlmostEqual(mgr.coordinator.data["window_usage_l"], 63.0, places=0)
            window_end(self.hass, local(6, 3, 1))
            self.assertEqual(mgr.coordinator.data["total_regenerations"], 1)
        self.run_async(run())

    def test_failed_platform_setup_stops_manager(self):  # N6
        async def run():
            await async_setup(self.hass, {})

            async def boom(entry, platforms):
                raise RuntimeError("Plattform kaputt")

            ok = self.hass.config_entries.async_forward_entry_setups
            self.hass.config_entries.async_forward_entry_setups = boom
            with self.assertRaises(RuntimeError):
                await async_setup_entry(self.hass, self.entry)
            self.assertEqual(self.hass.timers, [])
            self.assertNotIn("abc123", self.hass.data["water_softener_refill_sensor"])
            self.hass.config_entries.async_forward_entry_setups = ok
            await async_setup_entry(self.hass, self.entry)
            self.assertEqual(len(self.hass.timers), 1)
        self.run_async(run())

    def test_update_entity_refresh(self):  # N2
        async def run():
            mgr = await self._setup()
            await mgr.coordinator.async_request_refresh()
            self.assertEqual(mgr.coordinator.data["salt_stock_kg"], 100.0)
        self.run_async(run())

    def test_options_change_during_open_window(self):
        async def run():
            mgr = await self._setup()
            push(self.hass, 1030, local(6, 2, 10))  # 30 L bei Schwelle 45
            await mgr.async_stop()  # Optionen geändert: Neuladen mit Schwelle 25
            self.entry.options = {"threshold_l": 25}
            await async_setup_entry(self.hass, self.entry)
            mgr2 = self.hass.data["water_softener_refill_sensor"]["abc123"]
            self.assertEqual(mgr2.model.state.window_usage_l, 30.0)
            window_end(self.hass, local(6, 3, 1))
            self.assertEqual(mgr2.coordinator.data["total_regenerations"], 1)
        self.run_async(run())


class ConfigFlowHelpers(unittest.TestCase):
    def test_normalize_and_validate(self):
        data = config_flow._normalize(
            {"name": "X", "water_entity": "sensor.w", "capacity_kg": "25", "per_regen_kg": 1.5, "threshold_l": 45.0,
             "window_start_hour": 2.0, "window_end_hour": 3.0, "warn_remaining": 3.0}
        )
        self.assertEqual(data["window_start_hour"], 2)
        self.assertIsInstance(data["threshold_l"], int)
        self.assertEqual(config_flow._validate(data), {})
        self.assertEqual(config_flow._validate({**data, "window_end_hour": 2}), {"base": "window_invalid"})
        self.assertEqual(config_flow._validate({**data, "per_regen_kg": 30.0}), {"base": "per_regen_too_large"})
        self.assertEqual(config_flow._validate({**data, "initial_stock_kg": 99.0}), {"base": "stock_too_large"})

    def test_schema_builds(self):
        config_flow._schema(True, {})
        config_flow._schema(False, {"water_entity": "sensor.w"})

    def test_number_selector_never_gets_unit_none(self):
        """Home Assistant lehnt unit_of_measurement=None ab (Formular bricht mit 400: Bad Request ab)."""
        seen = []
        original = config_flow.NumberSelectorConfig
        config_flow.NumberSelectorConfig = lambda **kw: seen.append(kw) or kw
        try:
            config_flow._schema(True, {})
            config_flow._schema(False, {"water_entity": "sensor.w"})
        finally:
            config_flow.NumberSelectorConfig = original
        self.assertTrue(seen)
        for kw in seen:
            if "unit_of_measurement" in kw:
                self.assertIsInstance(kw["unit_of_measurement"], str)


if __name__ == "__main__":
    unittest.main()
