"""Einrichtung und Optionen der Enthärtungsanlage über die Home-Assistant-Oberfläche."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import (
    CONF_CAPACITY_KG,
    CONF_INITIAL_STOCK_KG,
    CONF_PER_REGEN_KG,
    CONF_THRESHOLD_L,
    CONF_WARN_REMAINING,
    CONF_WATER_ENTITY,
    CONF_WINDOW_END,
    CONF_WINDOW_START,
    DEFAULT_CAPACITY_KG,
    DEFAULT_NAME,
    DEFAULT_PER_REGEN_KG,
    DEFAULT_THRESHOLD_L,
    DEFAULT_WARN_REMAINING,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    DOMAIN,
)


def _number(minimum: float, maximum: float, step: float, unit: str | None = None) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=NumberSelectorMode.BOX
        )
    )


def _schema(first_setup: bool, defaults: dict[str, Any]) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if first_setup:
        fields[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME))] = TextSelector()
    fields[vol.Required(CONF_WATER_ENTITY, default=defaults.get(CONF_WATER_ENTITY, vol.UNDEFINED))] = EntitySelector(
        EntitySelectorConfig(domain="sensor")
    )
    fields[vol.Required(CONF_CAPACITY_KG, default=defaults.get(CONF_CAPACITY_KG, DEFAULT_CAPACITY_KG))] = _number(
        1, 1000, 0.5, "kg"
    )
    fields[vol.Required(CONF_PER_REGEN_KG, default=defaults.get(CONF_PER_REGEN_KG, DEFAULT_PER_REGEN_KG))] = _number(
        0.01, 100, 0.01, "kg"
    )
    if first_setup:
        # Optional: aktueller Füllstand beim Einrichten (leer = Behälter voll)
        fields[vol.Optional(CONF_INITIAL_STOCK_KG)] = _number(0, 1000, 0.5, "kg")
    fields[vol.Required(CONF_THRESHOLD_L, default=defaults.get(CONF_THRESHOLD_L, DEFAULT_THRESHOLD_L))] = _number(
        1, 5000, 1, "L"
    )
    fields[vol.Required(CONF_WINDOW_START, default=defaults.get(CONF_WINDOW_START, DEFAULT_WINDOW_START))] = _number(
        0, 22, 1, "h"
    )
    fields[vol.Required(CONF_WINDOW_END, default=defaults.get(CONF_WINDOW_END, DEFAULT_WINDOW_END))] = _number(
        1, 23, 1, "h"
    )
    fields[vol.Required(CONF_WARN_REMAINING, default=defaults.get(CONF_WARN_REMAINING, DEFAULT_WARN_REMAINING))] = (
        _number(0, 100, 1)
    )
    return vol.Schema(fields)


def _normalize(user_input: dict[str, Any]) -> dict[str, Any]:
    """Zahlenfelder des Formulars (Kommazahlen) in passende Typen umwandeln."""
    data = dict(user_input)
    for key in (CONF_WINDOW_START, CONF_WINDOW_END, CONF_WARN_REMAINING, CONF_THRESHOLD_L):
        if key in data:
            data[key] = int(round(float(data[key])))
    for key in (CONF_CAPACITY_KG, CONF_PER_REGEN_KG, CONF_INITIAL_STOCK_KG):
        if key in data:
            data[key] = float(data[key])
    return data


def _validate(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if data[CONF_WINDOW_START] >= data[CONF_WINDOW_END]:
        errors["base"] = "window_invalid"
    elif data[CONF_PER_REGEN_KG] > data[CONF_CAPACITY_KG]:
        errors["base"] = "per_regen_too_large"
    elif data.get(CONF_INITIAL_STOCK_KG) is not None and data[CONF_INITIAL_STOCK_KG] > data[CONF_CAPACITY_KG]:
        errors["base"] = "stock_too_large"
    return errors


class EnthaertungConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung der Enthärtungsanlage."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        defaults: dict[str, Any] = {}
        if user_input is not None:
            data = _normalize(user_input)
            errors = _validate(data)
            if not errors:
                return self.async_create_entry(title=data[CONF_NAME], data=data)
            defaults = data
        return self.async_show_form(step_id="user", data_schema=_schema(True, defaults), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EnthaertungOptionsFlow()


class EnthaertungOptionsFlow(OptionsFlow):
    """Einstellungen nachträglich ändern (Behältergröße, Salzverbrauch, Zeitfenster, Schwellwert, Warnung)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            data = _normalize(user_input)
            errors = _validate(data)
            if not errors:
                return self.async_create_entry(title="", data=data)
            current = {**current, **data}
        return self.async_show_form(step_id="init", data_schema=_schema(False, current), errors=errors)
