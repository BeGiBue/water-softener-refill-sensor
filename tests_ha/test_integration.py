"""Anbindung mit echtem Home Assistant: Formulare, Entitäten, Dienste, Zeitplan, Einheiten, Laden/Entladen.

Die Attrappen in tests/ha_stubs.py prüfen nur den eigenen Ablauf. Fehler wie „400: Bad Request“ (1.1.0) oder falsche
Signaturen fallen nur hier auf.
"""
from __future__ import annotations

import logging
import pathlib
from unittest.mock import patch

import pytest
import voluptuous as vol
import yaml
from homeassistant import config_entries
from homeassistant.components import persistent_notification as pn
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.water_softener_refill_sensor import (
    SCHEMA_ADD,
    SCHEMA_REFILL,
    SCHEMA_SET_LAST,
    SCHEMA_SET_SINCE,
    SCHEMA_SET_STOCK,
)
from custom_components.water_softener_refill_sensor.const import DOMAIN

ROOT = pathlib.Path(__file__).resolve().parents[1]
W = "sensor.wasser"
DATA = {
    "name": "Enthärtungsanlage",
    "water_entity": W,
    "capacity_kg": 25.0,
    "per_regen_kg": 1.28,
    "threshold_l": 45,
    "window_start_hour": 2,
    "window_end_hour": 3,
    "warn_remaining": 3,
}
TOTAL = "sensor.enthartungsanlage_regenerationen_gesamt"
USAGE = "sensor.enthartungsanlage_verbrauch_im_zeitfenster"
STOCK = "sensor.enthartungsanlage_salzbestand"
LAST = "sensor.enthartungsanlage_letzte_regeneration"


@pytest.fixture
async def berlin(hass: HomeAssistant):
    await hass.config.async_set_time_zone("Europe/Berlin")
    hass.config.language = "de"
    return hass


def notifications(hass: HomeAssistant) -> dict:
    return pn._async_get_or_create_notifications(hass)


async def setup_entry(hass, freezer, when, value="1000", unit="L", **data):
    freezer.move_to(when)
    hass.states.async_set(W, value, {"unit_of_measurement": unit} if unit else {})
    entry = MockConfigEntry(domain=DOMAIN, data={**DATA, **data}, title="Enthärtungsanlage")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def meter(hass, freezer, when, value, unit="L"):
    freezer.move_to(when)
    hass.states.async_set(W, value, {"unit_of_measurement": unit} if unit else {})
    await hass.async_block_till_done()


async def tick(hass, freezer, when):
    freezer.move_to(when)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def state(hass, entity_id):
    return hass.states.get(entity_id).state


# ---------------------------------------------------------------- Formulare
async def test_config_flow_creates_entry(hass: HomeAssistant, berlin):
    hass.states.async_set(W, "1.000", {"unit_of_measurement": "m³"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    form = {**DATA, "threshold_l": 45.0, "window_start_hour": 2.0, "window_end_hour": 3.0, "warn_remaining": 3.0}
    bad = await hass.config_entries.flow.async_configure(result["flow_id"], {**form, "window_end_hour": 2.0})
    assert bad["errors"] == {"base": "window_invalid"}
    done = await hass.config_entries.flow.async_configure(bad["flow_id"], form)
    await hass.async_block_till_done()
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["data"]["warn_remaining"] == 3
    entry = done["result"]
    ids = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    assert len(ids) == 16
    assert {TOTAL, STOCK, "binary_sensor.enthartungsanlage_salz_nachfullen"} <= ids


async def test_options_flow_reload_keeps_state(hass: HomeAssistant, berlin, freezer):
    entry = await setup_entry(hass, freezer, "2026-10-06 12:00:00+02:00")
    await hass.services.async_call(DOMAIN, "add_regeneration", {"count": 2}, blocking=True)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    form = {k: v for k, v in DATA.items() if k != "name"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {**form, "capacity_kg": 20.0})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.state is ConfigEntryState.LOADED
    assert state(hass, TOTAL) == "2"
    assert float(state(hass, STOCK)) == 20.0  # auf die neue Behältergröße begrenzt


# ---------------------------------------------------------------- Nacht und Zeitplan
async def test_normal_night(hass: HomeAssistant, berlin, freezer):
    await setup_entry(hass, freezer, "2026-10-06 01:50:00+02:00")
    for t, v in [("02:10", "1010"), ("02:20", "1030"), ("02:40", "1050"), ("02:55", "1052")]:
        await meter(hass, freezer, f"2026-10-06 {t}:00+02:00", v)
    await tick(hass, freezer, "2026-10-06 03:00:59+02:00")
    assert state(hass, TOTAL) == "0"
    await tick(hass, freezer, "2026-10-06 03:01:00+02:00")
    assert state(hass, TOTAL) == "1"
    assert state(hass, LAST) == "2026-10-06T00:40:00+00:00"
    # nächste Nacht ohne Verbrauch: Zeitplan läuft weiter, Fenster mit 0 l abgeschlossen
    await tick(hass, freezer, "2026-10-07 03:01:00+02:00")
    assert float(state(hass, USAGE)) == 0.0


async def test_october_night_dst(hass: HomeAssistant, berlin, freezer):
    """25.10.2026: Fenster 02:00 MESZ bis 02:00 MEZ, Auswertung 02:01 MEZ (01:01 UTC), keine Doppelerfassung."""
    await setup_entry(hass, freezer, "2026-10-25 01:30:00+02:00")
    await meter(hass, freezer, "2026-10-25 02:30:00+02:00", "1025")  # erste 02:30 (MESZ)
    await tick(hass, freezer, "2026-10-25 01:00:30+00:00")  # 02:00:30 MEZ: Nachlauf, noch keine Auswertung
    assert hass.states.get(USAGE).state == "25.0"
    await tick(hass, freezer, "2026-10-25 01:01:00+00:00")  # 02:01 MEZ: Auswertung
    await meter(hass, freezer, "2026-10-25 02:30:00+01:00", "1050")  # zweite 02:30 (MEZ): nach dem Fenster
    assert state(hass, TOTAL) == "0"
    assert float(state(hass, USAGE)) == 25.0


async def test_march_night_dst(hass: HomeAssistant, berlin, freezer):
    """28.03.2027: 02:00 gibt es nicht. Fenster 03:00 bis 04:00 MESZ, Auswertung 04:01 MESZ."""
    await setup_entry(hass, freezer, "2027-03-28 01:59:00+01:00")
    await meter(hass, freezer, "2027-03-28 03:10:00+02:00", "1020")
    await tick(hass, freezer, "2027-03-28 03:01:30+02:00")
    await meter(hass, freezer, "2027-03-28 03:40:00+02:00", "1052")
    assert state(hass, TOTAL) == "0"  # nicht zu früh ausgewertet
    await tick(hass, freezer, "2027-03-28 04:01:00+02:00")
    assert state(hass, TOTAL) == "1"
    assert state(hass, LAST) == "2027-03-28T01:40:00+00:00"


async def test_catch_up_after_restart(hass: HomeAssistant, berlin, freezer):
    entry = await setup_entry(hass, freezer, "2026-10-06 01:50:00+02:00")
    await meter(hass, freezer, "2026-10-06 02:10:00+02:00", "1030")
    await meter(hass, freezer, "2026-10-06 02:20:00+02:00", "1052")
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.move_to("2026-10-06 07:00:00+02:00")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert state(hass, TOTAL) == "1"


# ---------------------------------------------------------------- Einheiten (M3)
@pytest.mark.parametrize(
    ("unit", "start", "end"),
    [("L", "1000", "1053"), ("m³", "1.000", "1.053"), ("gal", "100", "114"), ("ft³", "10", "11.9")],
)
async def test_units_are_converted(hass: HomeAssistant, berlin, freezer, unit, start, end):
    await setup_entry(hass, freezer, "2026-10-06 01:50:00+02:00", value=start, unit=unit)
    await meter(hass, freezer, "2026-10-06 02:30:00+02:00", end, unit)
    await tick(hass, freezer, "2026-10-06 03:01:00+02:00")
    assert state(hass, TOTAL) == "1", float(state(hass, USAGE))
    assert 50 < float(state(hass, USAGE)) < 56


async def test_unknown_or_missing_unit(hass: HomeAssistant, berlin, freezer, caplog):
    entry = await setup_entry(hass, freezer, "2026-10-06 01:50:00+02:00", unit="Eimer")
    nid = f"{DOMAIN}_{entry.entry_id}_unit"
    assert nid in notifications(hass)
    assert notifications(hass)[nid]["title"] == "Einheit des Wasserzählers unbekannt"
    assert caplog.text.count("keine bekannte Volumeneinheit") == 1
    await meter(hass, freezer, "2026-10-06 02:10:00+02:00", "1100", "Eimer")
    assert caplog.text.count("keine bekannte Volumeneinheit") == 1  # nur einmal
    await meter(hass, freezer, "2026-10-06 02:20:00+02:00", "1200", None)  # ohne Einheit
    await meter(hass, freezer, "2026-10-06 02:30:00+02:00", "1300", "L")  # bekannt: nur Bezugswert
    assert nid not in notifications(hass)
    await meter(hass, freezer, "2026-10-06 02:40:00+02:00", "1320", "L")
    await tick(hass, freezer, "2026-10-06 03:01:00+02:00")
    assert float(state(hass, USAGE)) == 20.0
    assert state(hass, TOTAL) == "0"


async def test_unit_change_sets_baseline(hass: HomeAssistant, berlin, freezer):
    await setup_entry(hass, freezer, "2026-10-06 01:50:00+02:00")
    await meter(hass, freezer, "2026-10-06 02:10:00+02:00", "1010")
    await meter(hass, freezer, "2026-10-06 02:20:00+02:00", "5.000", "m³")  # Zählertausch: nur Bezugswert
    await meter(hass, freezer, "2026-10-06 02:30:00+02:00", "5.020", "m³")
    assert float(state(hass, USAGE)) == 30.0


# ---------------------------------------------------------------- Dienste
async def test_services(hass: HomeAssistant, berlin, freezer):
    await setup_entry(hass, freezer, "2026-10-09 15:00:00+02:00")
    await hass.services.async_call(
        DOMAIN, "add_regeneration", {"count": 1, "datetime": "2026-10-07 02:30:00"}, blocking=True
    )
    assert state(hass, LAST) == "2026-10-07T00:30:00+00:00"
    assert state(hass, "sensor.enthartungsanlage_nachste_regeneration_spatestens") == "2026-10-14T00:00:00+00:00"
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "add_regeneration", {"datetime": "2026-10-10 02:30:00"}, blocking=True
        )
    assert err.value.translation_key == "datetime_in_future"
    assert str(err.value) == "The time must not be in the future"  # Text aus en.json gefunden
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "refill", {"kg": 0}, blocking=True)
    await hass.services.async_call(DOMAIN, "refill", {"kg": 0.01}, blocking=True)
    await hass.services.async_call(DOMAIN, "set_regenerations_since_refill", {"count": 16}, blocking=True)
    await hass.services.async_call(DOMAIN, "set_salt_stock", {"kg": 3}, blocking=True)
    assert state(hass, "sensor.enthartungsanlage_regenerationen_seit_nachfullen") == "16"  # unabhängig vom Bestand
    await hass.services.async_call(DOMAIN, "set_last_regeneration", {"datetime": "2026-10-08 02:30:00"}, blocking=True)
    assert state(hass, LAST) == "2026-10-08T00:30:00+00:00"
    # Eingabe + Taste
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.enthartungsanlage_nachgefullte_salzmenge", "value": 5},
        blocking=True,
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.enthartungsanlage_salz_nachgefullt"}, blocking=True
    )
    assert float(state(hass, STOCK)) == 8.0
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.enthartungsanlage_salz_nachgefullt"}, blocking=True
        )
    assert err.value.translation_key == "refill_amount_required"


async def test_two_entries(hass: HomeAssistant, berlin, freezer):
    first = await setup_entry(hass, freezer, "2026-10-09 15:00:00+02:00")
    second = MockConfigEntry(domain=DOMAIN, data={**DATA, "name": "Zweite"}, title="Zweite")
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "add_regeneration", {}, blocking=True)
    assert err.value.translation_key == "multiple_entries"
    await hass.services.async_call(DOMAIN, "add_regeneration", {"config_entry": second.entry_id}, blocking=True)
    assert state(hass, TOTAL) == "0"
    assert state(hass, "sensor.zweite_regenerationen_gesamt") == "1"
    assert first.state is ConfigEntryState.LOADED


def test_services_yaml_matches_schemas():
    """services.yaml beschreibt genau die Felder der Schemas (Pflicht/optional gleich)."""
    path = ROOT / "custom_components" / DOMAIN / "services.yaml"
    services = yaml.safe_load(path.read_text(encoding="utf-8"))
    schemas = {
        "refill": SCHEMA_REFILL,
        "set_salt_stock": SCHEMA_SET_STOCK,
        "add_regeneration": SCHEMA_ADD,
        "set_last_regeneration": SCHEMA_SET_LAST,
        "set_regenerations_since_refill": SCHEMA_SET_SINCE,
    }
    assert set(services) == set(schemas)
    for name, schema in schemas.items():
        fields = services[name]["fields"]
        keys = {str(k): isinstance(k, vol.Required) for k in schema.schema}
        assert set(fields) == set(keys), name
        for field, required in keys.items():
            assert bool(fields[field].get("required", False)) == required, f"{name}.{field}"
    assert services["refill"]["fields"]["kg"]["selector"]["number"]["min"] > 0
    with pytest.raises(vol.Invalid):
        SCHEMA_REFILL({"kg": 0})


# ---------------------------------------------------------------- Laden, Entladen, Fehler
async def test_update_entity_writes_no_error(hass: HomeAssistant, berlin, freezer, caplog):
    await async_setup_component(hass, "homeassistant", {})
    await setup_entry(hass, freezer, "2026-10-06 12:00:00+02:00")
    caplog.clear()
    await hass.services.async_call("homeassistant", "update_entity", {"entity_id": STOCK}, blocking=True)
    await hass.async_block_till_done()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert state(hass, STOCK) == "25.0"


async def test_unload_dismisses_notifications_and_load_recreates(hass: HomeAssistant, berlin, freezer):
    entry = await setup_entry(hass, freezer, "2026-10-01 12:00:00+02:00")
    await hass.services.async_call(DOMAIN, "set_last_regeneration", {"datetime": "2026-09-20 02:30:00"}, blocking=True)
    await hass.services.async_call(DOMAIN, "set_salt_stock", {"kg": 1}, blocking=True)
    ids = {f"{DOMAIN}_{entry.entry_id}_low_salt", f"{DOMAIN}_{entry.entry_id}_overdue"}
    assert ids <= set(notifications(hass))
    assert "am Fälligkeitstag (27.09.2026)" in notifications(hass)[f"{DOMAIN}_{entry.entry_id}_overdue"]["message"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not ids & set(notifications(hass))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ids <= set(notifications(hass))
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not ids & set(notifications(hass))


async def test_failed_setup_leaves_no_second_manager(hass: HomeAssistant, berlin, freezer):
    from custom_components.water_softener_refill_sensor.manager import SoftenerManager

    stopped = []
    original_stop = SoftenerManager.async_stop

    async def recording_stop(self):
        stopped.append(self)
        await original_stop(self)

    freezer.move_to("2026-10-06 01:50:00+02:00")
    hass.states.async_set(W, "1000", {"unit_of_measurement": "L"})
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, title="Enthärtungsanlage")
    entry.add_to_hass(hass)
    with (
        patch.object(hass.config_entries, "async_forward_entry_setups", side_effect=RuntimeError("kaputt")),
        patch.object(SoftenerManager, "async_stop", recording_stop),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(stopped) == 1
    assert stopped[0]._unsubs == [] and stopped[0]._unsub_timer is None
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert list(hass.data[DOMAIN]) == [entry.entry_id]
