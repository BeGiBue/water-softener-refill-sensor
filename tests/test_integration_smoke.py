"""Ablauftest der Home-Assistant-Anbindung mit Attrappen (siehe ha_stubs.py).

Spielt eine Nacht durch: Zählerstände -> Regeneration erkannt -> Salzbestand -> Meldung -> Bestätigung.
"""
import asyncio
import os
import sys
import types
import unittest
from datetime import datetime

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
        self.time_cbs = []
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
    FakeDt._now = when
    for hour, minute, second, cb in hass.time_cbs:
        cb(when)


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
        # Zeitplan: Auswertung um 03:01:00
        self.assertEqual([(h, m, s) for h, m, s, _ in hass.time_cbs], [(3, 1, 0)])

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

    def test_english_notification(self):
        hass, entry = self.start(capacity_kg=8.0)  # Restbestand 2 → sofort Meldung
        hass.config.language = "en"
        asyncio.run(async_setup_entry(hass, entry))
        note = FakeNotifications.active["water_softener_refill_sensor_abc123_low_salt"]
        self.assertEqual(note["title"], "Refill salt")
        self.assertIn("2 more regenerations", note["message"])


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
