"""Taste: Nachfüllen mit der eingegebenen Menge bestätigen."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EnthaertungEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ConfirmRefillButton(manager, entry), ConfirmFullButton(manager, entry)])


class ConfirmRefillButton(EnthaertungEntity, ButtonEntity):
    """Bestätigt, dass Salz nachgefüllt wurde: die Menge aus „Nachgefüllte Salzmenge“ wird zum Bestand addiert."""

    _attr_icon = "mdi:check-bold"

    def __init__(self, manager, entry: ConfigEntry) -> None:
        super().__init__(manager.coordinator, entry, "confirm_refill")
        self._manager = manager

    async def async_press(self) -> None:
        await self._manager.async_refill(self._manager.refill_input_kg)


class ConfirmFullButton(EnthaertungEntity, ButtonEntity):
    """Setzt den Salzbestand mit einem Knopfdruck auf voll (Behältergröße) und beendet die Meldung."""

    _attr_icon = "mdi:tray-full"

    def __init__(self, manager, entry: ConfigEntry) -> None:
        super().__init__(manager.coordinator, entry, "confirm_full")
        self._manager = manager

    async def async_press(self) -> None:
        await self._manager.async_refill_full()
