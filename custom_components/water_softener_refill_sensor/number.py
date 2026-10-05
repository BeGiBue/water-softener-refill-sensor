"""Eingabe: nachgefüllte Salzmenge (kg), die mit der Taste „Salz nachgefüllt“ bestätigt wird."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EnthaertungEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RefillAmountNumber(manager, entry)])


class RefillAmountNumber(EnthaertungEntity, NumberEntity):
    """Menge in kg, die nachgefüllt wurde. Wird beim Bestätigen (Taste oder Dienst) zurück auf 0 gesetzt."""

    _attr_icon = "mdi:scale-bathroom"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS

    def __init__(self, manager, entry: ConfigEntry) -> None:
        super().__init__(manager.coordinator, entry, "refill_amount")
        self._manager = manager

    @property
    def native_max_value(self) -> float:
        return float(self._manager.settings.capacity_kg)

    @property
    def native_value(self) -> float:
        return float(self.coordinator.data["refill_input_kg"])

    async def async_set_native_value(self, value: float) -> None:
        self._manager.set_refill_input(value)
