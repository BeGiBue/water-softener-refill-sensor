"""Minimale Attrappen der Home-Assistant-Schnittstellen, damit die Anbindung ohne Home Assistant geprüft werden kann.

Das prüft den *eigenen* Code (Abläufe, Namen), nicht die Kompatibilität zur echten Home-Assistant-API.
Maßgeblich für die Anbindung an Home Assistant sind die Tests mit echtem Home Assistant in `tests_ha/`
(pytest-homeassistant-custom-component). Damit neue Importe nicht unbemerkt durch die Attrappen rutschen, liefert der
Finder nur die unten in ALLOWED_MODULES aufgeführten Module; ein neues Modul muss hier bewusst ergänzt werden.
"""
from __future__ import annotations

import importlib.abc
import importlib.util
import json
import os
import sys
import types
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")


# ---------------------------------------------------------------- automatische Attrappen
class _Meta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return f"{cls.__name__}.{name}"


def _cls(name: str):
    return _Meta(
        name,
        (object,),
        {
            "__init__": lambda self, *a, **k: self.__dict__.update(k),
            "__class_getitem__": classmethod(lambda c, i: c),
        },
    )


class _AutoModule(types.ModuleType):
    __path__: list = []

    def __call__(self, *a, **k):  # Module dürfen wie Funktionen aufgerufen werden (z. B. cv.string(...))
        return _cls("Call")(**k)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name[0].isupper():
            obj = _cls(name)
        elif f"{self.__name__}.{name}" in ALLOWED_MODULES or f"{self.__name__}.{name}" in sys.modules:
            obj = importlib.import_module(f"{self.__name__}.{name}")  # Untermodul
        else:  # Funktion (z. B. cv.string, cv.config_entry_only_config_schema)
            obj = _AutoModule(f"{self.__name__}.{name}")
        setattr(self, name, obj)
        return obj


class _Loader(importlib.abc.Loader):
    def create_module(self, spec):
        return _AutoModule(spec.name)

    def exec_module(self, module):
        pass


# Module, die die Integration importieren darf (alles andere schlägt wie ein fehlendes Modul fehl)
ALLOWED_MODULES = {
    "voluptuous",
    "homeassistant.components.datetime",
    "homeassistant.components.number",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.selector",
    "homeassistant.helpers.translation",
    "homeassistant.helpers.typing",
}


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name in ALLOWED_MODULES:
            return importlib.util.spec_from_loader(name, _Loader(), is_package=True)
        if name == "homeassistant" or name.startswith("homeassistant."):
            raise ModuleNotFoundError(f"Attrappe fehlt für {name} (in tests/ha_stubs.py ergänzen)")
        return None


def _module(name: str, **attrs: Any) -> types.ModuleType:
    mod = _AutoModule(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------- explizite Attrappen
class FakeStore:
    DATA: dict[str, Any] = {}

    def __init__(self, hass, version, key, **kw):
        self.key = key

    async def async_load(self):
        return FakeStore.DATA.get(self.key)

    async def async_save(self, data):
        FakeStore.DATA[self.key] = data

    def async_delay_save(self, data_func, delay=0):
        FakeStore.DATA[self.key] = data_func()

    async def async_remove(self):
        FakeStore.DATA.pop(self.key, None)


class FakeCoordinator:
    def __init__(self, hass, logger, *, config_entry=None, name=None, update_method=None, **kw):
        self.data = None
        self.updates = 0
        self.update_method = update_method

    async def async_request_refresh(self):
        self.async_set_updated_data(await self.update_method())

    def async_set_updated_data(self, data):
        self.data = data
        self.updates += 1


class FakeCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def __class_getitem__(cls, item):
        return cls


class FakeNotifications:
    active: dict[str, dict[str, Any]] = {}
    log: list[tuple] = []

    @classmethod
    def async_create(cls, hass, message, title=None, notification_id=None):
        cls.active[notification_id] = {"title": title, "message": message}
        cls.log.append(("create", notification_id, title))

    @classmethod
    def async_dismiss(cls, hass, notification_id):
        if cls.active.pop(notification_id, None) is not None:
            cls.log.append(("dismiss", notification_id))


class FakeDt:
    _now = datetime(2026, 10, 5, 12, 0, tzinfo=TZ)

    @classmethod
    def now(cls):
        return cls._now

    @staticmethod
    def as_local(d):
        return d.astimezone(TZ)

    @staticmethod
    def as_utc(d):
        return d.astimezone(ZoneInfo("UTC"))

    @staticmethod
    def get_default_time_zone():
        return TZ


@dataclass(frozen=True, kw_only=True)
class FakeDescription:
    key: str
    translation_key: str | None = None
    device_class: Any = None
    native_unit_of_measurement: Any = None
    state_class: Any = None
    icon: str | None = None
    entity_category: Any = None
    suggested_display_precision: int | None = None


class FakeConfigFlow:
    def __init_subclass__(cls, domain=None, **kw):
        cls.domain = domain


class ServiceValidationError(Exception):
    def __init__(self, *args, translation_domain=None, translation_key=None, translation_placeholders=None):
        super().__init__(*args)
        self.translation_domain = translation_domain
        self.translation_key = translation_key
        self.translation_placeholders = translation_placeholders


class FakeVolumeConverter:
    _TO_L = {"L": 1.0, "mL": 0.001, "m³": 1000.0, "gal": 3.785411784, "ft³": 28.316846592, "CCF": 2831.6846592,
             "MCF": 28316.846592, "fl. oz.": 0.0295735295625}
    VALID_UNITS = set(_TO_L)

    @classmethod
    def convert(cls, value, from_unit, to_unit):
        return value * cls._TO_L[from_unit] / cls._TO_L[to_unit]


_TRANSLATIONS = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "water_softener_refill_sensor", "translations"
)


async def fake_async_get_translations(hass, language, category, integrations=None, config_flow=None):
    """Wie Home Assistant: flache Schlüssel component.<domain>.<category>.…, Rückfall auf Englisch."""
    out = {}
    for lang in ("en", language):
        path = os.path.join(_TRANSLATIONS, f"{lang}.json")
        if not os.path.exists(path):
            continue

        def walk(node, prefix):
            for key, value in node.items():
                if isinstance(value, dict):
                    walk(value, f"{prefix}.{key}")
                else:
                    out[f"{prefix}.{key}"] = value

        with open(path, encoding="utf-8") as fh:
            walk(json.load(fh).get(category, {}), f"component.water_softener_refill_sensor.{category}")
    return out


def _track_point(hass, action, point):
    entry = (point, action)
    hass.timers.append(entry)

    def cancel():
        if entry in hass.timers:
            hass.timers.remove(entry)

    return cancel


def install() -> None:
    """Attrappen registrieren (vor dem Import der Integration aufrufen)."""
    sys.meta_path.append(_Finder())
    _module("homeassistant")
    _module(
        "homeassistant.const",
        STATE_UNAVAILABLE="unavailable",
        STATE_UNKNOWN="unknown",
        PERCENTAGE="%",
        CONF_NAME="name",
    )
    _module("homeassistant.core", callback=lambda f: f)
    _module("homeassistant.exceptions", ServiceValidationError=ServiceValidationError)
    _module("homeassistant.config_entries", ConfigFlow=FakeConfigFlow)
    _module("homeassistant.helpers")
    _module("homeassistant.helpers.storage", Store=FakeStore)
    _module(
        "homeassistant.helpers.event",
        async_track_state_change_event=lambda hass, ids, action: (hass.state_cbs.append(action) or (lambda: None)),
        async_track_point_in_utc_time=_track_point,
    )
    _module("homeassistant.helpers.translation", async_get_translations=fake_async_get_translations)
    _module(
        "homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=FakeCoordinator,
        CoordinatorEntity=FakeCoordinatorEntity,
    )
    _module("homeassistant.components")
    _module(
        "homeassistant.components.persistent_notification",
        async_create=FakeNotifications.async_create,
        async_dismiss=FakeNotifications.async_dismiss,
    )
    sys.modules["homeassistant.components"].persistent_notification = sys.modules[
        "homeassistant.components.persistent_notification"
    ]
    _module("homeassistant.components.sensor", SensorEntityDescription=FakeDescription)
    _module("homeassistant.components.binary_sensor")
    _module("homeassistant.components.button")
    _module("homeassistant.util.unit_conversion", VolumeConverter=FakeVolumeConverter)
    dt_mod = _module(
        "homeassistant.util.dt",
        now=FakeDt.now,
        as_local=FakeDt.as_local,
        as_utc=FakeDt.as_utc,
        get_default_time_zone=FakeDt.get_default_time_zone,
    )
    _module("homeassistant.util", dt=dt_mod)
