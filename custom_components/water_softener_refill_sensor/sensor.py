"""Sensoren: Regenerationen, Salzbestand, Restbestand, letzte Regeneration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfMass, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EnthaertungEntity


@dataclass(frozen=True, kw_only=True)
class EnthaertungSensorDescription(SensorEntityDescription):
    """Beschreibung eines Sensors mit Funktion, die den Wert aus den Manager-Daten liest."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSORS: tuple[EnthaertungSensorDescription, ...] = (
    EnthaertungSensorDescription(
        key="total_regenerations",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d["total_regenerations"],
    ),
    EnthaertungSensorDescription(
        key="regenerations_since_refill",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["regenerations_since_refill"],
    ),
    EnthaertungSensorDescription(
        key="salt_stock",
        icon="mdi:shaker-outline",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d["salt_stock_kg"],
        attrs_fn=lambda d: {"capacity_kg": d["capacity_kg"], "per_regeneration_kg": d["per_regen_kg"]},
    ),
    EnthaertungSensorDescription(
        key="salt_level",
        icon="mdi:gauge",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: d["salt_percent"],
    ),
    EnthaertungSensorDescription(
        key="regenerations_left",
        icon="mdi:shaker",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["regenerations_left"],
        attrs_fn=lambda d: {"warn_at": d["warn_remaining"]},
    ),
    EnthaertungSensorDescription(
        key="last_regeneration",
        icon="mdi:water-sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d["last_regeneration"],
        attrs_fn=lambda d: {"history": d["history"]},
    ),
    EnthaertungSensorDescription(
        key="next_regeneration_due",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d["next_regeneration_due"],
    ),
    EnthaertungSensorDescription(
        key="last_refill",
        icon="mdi:shaker-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["last_refill"],
    ),
    EnthaertungSensorDescription(
        key="window_usage",
        icon="mdi:water",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda d: d["window_usage_l"],
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(EnthaertungSensor(manager.coordinator, entry, description) for description in SENSORS)


class EnthaertungSensor(EnthaertungEntity, SensorEntity):
    """Sensor der Enthärtungsanlage."""

    entity_description: EnthaertungSensorDescription

    def __init__(self, coordinator, entry: ConfigEntry, description: EnthaertungSensorDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator.data) if fn else None
