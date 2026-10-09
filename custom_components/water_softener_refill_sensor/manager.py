"""Verwaltung der Regenerationszählung: Zählerstand überwachen, Zustand speichern, benachrichtigen."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_track_point_in_utc_time, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import VolumeConverter

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
    DEFAULT_PER_REGEN_KG,
    DEFAULT_THRESHOLD_L,
    DEFAULT_WARN_REMAINING,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    DOMAIN,
    SAVE_DELAY,
    STORAGE_VERSION,
    notification_id,
    overdue_notification_id,
    storage_key,
    unit_notification_id,
)
from .logic import Settings, SoftenerModel

_LOGGER = logging.getLogger(__name__)

LITERS = "L"
# Schreibweisen, die Home Assistant nicht als Volumeneinheit kennt, die aber eindeutig sind (Kleinschreibung)
UNIT_ALIASES = {"l": "L", "ℓ": "L", "liter": "L", "liters": "L", "ml": "mL", "m3": "m³", "m³": "m³"}


def normalize_volume_unit(unit: Any) -> str | None:
    """Einheit des Wasserzählers als Volumeneinheit von Home Assistant (L, mL, m³, gal, ft³, CCF …), sonst None."""
    if not isinstance(unit, str) or not unit.strip():
        return None
    unit = unit.strip()
    if unit in VolumeConverter.VALID_UNITS:
        return unit
    if (alias := UNIT_ALIASES.get(unit.lower())) is not None:
        return alias
    for valid in VolumeConverter.VALID_UNITS:
        if valid.lower() == unit.lower():
            return valid
    return None


def service_error(key: str, **placeholders: Any) -> ServiceValidationError:
    """Übersetzte Fehlermeldung (Texte unter „exceptions“ in translations/*.json)."""
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={k: str(v) for k, v in placeholders.items()} or None,
    )

MESSAGES = {
    "de": {
        "title": "Salz nachfüllen",
        "message": (
            "Der rechnerische Salzvorrat der Enthärtungsanlage „{name}“ reicht nur noch für {left} {unit} "
            "({stock} kg von {capacity} kg).\n\n"
            "Bitte Salz nachfüllen und die nachgefüllte Menge in kg bestätigen: Menge bei „Nachgefüllte Salzmenge“ "
            "(Gerät „{name}“) eingeben und Taste „Salz nachgefüllt“ drücken, bei vollem Behälter genügt die Taste "
            "„Behälter voll“, oder Dienst `water_softener_refill_sensor.refill` mit `kg` aufrufen. Diese Meldung bleibt bestehen, bis eine Menge bestätigt wurde und der Bestand wieder über der "
            "Warnschwelle liegt."
        ),
        "one": "Regeneration",
        "many": "Regenerationen",
        "overdue_title": "Regeneration überfällig",
        "overdue_message": (
            "Bei der Enthärtungsanlage „{name}“ wurde am Fälligkeitstag ({due}) keine Regeneration erkannt "
            "(letzte erkannte Regeneration: {last}). Die Anlage regeneriert spätestens 7 Tage nach der letzten "
            "Regeneration.\n\n"
            "Mögliche Ursachen: Der Wasserzähler war im Zeitfenster nicht verfügbar, oder die Anlage ist gestört. "
            "Eine tatsächlich erfolgte Regeneration lässt sich mit dem Dienst `water_softener_refill_sensor.add_regeneration` "
            "nachtragen (optional mit Zeitpunkt `datetime`). "
            "Diese Meldung verschwindet, sobald wieder eine Regeneration gezählt wird."
        ),
    },
    "en": {
        "title": "Refill salt",
        "message": (
            "The calculated salt stock of the water softener “{name}” only lasts for {left} more {unit} "
            "({stock} kg of {capacity} kg).\n\n"
            "Please refill salt and confirm the amount in kg: enter it at “Salt amount refilled” (device “{name}”) "
            "and press the button “Salt refilled”, press “Tank full” if the tank is full, or call the service `water_softener_refill_sensor.refill` with `kg`. This notice "
            "stays until an amount is confirmed and the stock is above the warning threshold again."
        ),
        "one": "regeneration",
        "many": "regenerations",
        "overdue_title": "Regeneration overdue",
        "overdue_message": (
            "No regeneration was detected for the water softener “{name}” on the due day ({due}) "
            "(last detected regeneration: {last}). The softener regenerates at the latest 7 days after the last "
            "regeneration.\n\n"
            "Possible causes: the water meter was unavailable during the time window, or the softener is faulty. "
            "A regeneration that did take place can be added with the service `water_softener_refill_sensor.add_regeneration` "
            "(optionally with the time `datetime`). "
            "This notice disappears as soon as a regeneration is counted again."
        ),
    },
}


def settings_from_entry(entry: ConfigEntry) -> Settings:
    cfg = {**entry.data, **entry.options}
    return Settings(
        capacity_kg=float(cfg.get(CONF_CAPACITY_KG, DEFAULT_CAPACITY_KG)),
        per_regen_kg=float(cfg.get(CONF_PER_REGEN_KG, DEFAULT_PER_REGEN_KG)),
        threshold_l=float(cfg.get(CONF_THRESHOLD_L, DEFAULT_THRESHOLD_L)),
        start_hour=int(cfg.get(CONF_WINDOW_START, DEFAULT_WINDOW_START)),
        end_hour=int(cfg.get(CONF_WINDOW_END, DEFAULT_WINDOW_END)),
        warn_remaining=int(cfg.get(CONF_WARN_REMAINING, DEFAULT_WARN_REMAINING)),
    )


class SoftenerManager:
    """Beobachtet den Wasserzähler, führt das Rechenmodell und stellt die Werte für die Entitäten bereit."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        cfg = {**entry.data, **entry.options}
        self.water_entity: str = cfg[CONF_WATER_ENTITY]
        self._initial_stock = cfg.get(CONF_INITIAL_STOCK_KG)
        self.settings = settings_from_entry(entry)
        self.model = SoftenerModel(self.settings, initial_stock_kg=self._initial_stock)
        self._store = Store(hass, STORAGE_VERSION, storage_key(entry.entry_id))
        # update_method liefert nur den aktuellen Schnappschuss (kein Polling); so schreibt
        # homeassistant.update_entity keinen Fehler ins Protokoll
        self.coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_method=self._async_update_data,
        )
        self._unsubs: list[Callable[[], None]] = []
        self._unsub_timer: Callable[[], None] | None = None
        self._need_baseline = True  # nach dem Start zuerst nur einen Bezugswert setzen
        self._last_unit: str | None = None  # Einheit des letzten gezählten Werts
        self._unit_problem: str | None = None  # unbekannte Einheit, für die eine Meldung besteht
        self._issue_texts: dict[str, str] = {}
        self.refill_input_kg: float = 0.0  # Eingabe der Nachfüllmenge für die Taste (nicht gespeichert)

    # ------------------------------------------------------------------ Start / Stopp
    async def async_start(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self.model = SoftenerModel.from_dict(self.settings, stored)
        self._issue_texts = await async_get_translations(self.hass, self.hass.config.language, "issues", {DOMAIN})
        now = dt_util.now()

        # Ein während der Abwesenheit beendetes Zeitfenster nachträglich auswerten
        events = self.model.evaluate_pending(now)
        if events:
            self._log_events(events)

        self._unsubs.append(async_track_state_change_event(self.hass, [self.water_entity], self._handle_state_event))
        self._schedule_evaluation(now)

        # aktuellen Zählerstand als Bezugswert übernehmen
        current = self.hass.states.get(self.water_entity)
        if current is not None:
            self._process_state(current, now)

        self._publish()
        self._update_notification()
        self._save_later()

    async def async_stop(self) -> None:
        self._cancel_timer()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self._store.async_save(self.model.to_dict())

    # ------------------------------------------------------------------ Zeitplan
    def _schedule_evaluation(self, now: datetime) -> None:
        """Auswertung zum nächsten Fensterende + 1 Minute in echter Zeit (UTC), auch in den Umstellungsnächten."""
        self._cancel_timer()
        point = self.model.next_evaluation(dt_util.as_local(now))
        self._unsub_timer = async_track_point_in_utc_time(self.hass, self._handle_window_end, dt_util.as_utc(point))

    def _cancel_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    # ------------------------------------------------------------------ Wasserzähler
    def _process_state(self, state: State, now) -> None:
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._need_baseline = True
            return
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return
        raw_unit = state.attributes.get("unit_of_measurement")
        unit = normalize_volume_unit(raw_unit)
        if unit is None:
            # Unbekannte oder fehlende Einheit: nichts zählen; der nächste Wert mit bekannter Einheit ist Bezugswert
            self._need_baseline = True
            self._report_unit_problem(str(raw_unit) if raw_unit else "–")
            return
        self._clear_unit_problem()
        baseline = self._need_baseline or (self._last_unit is not None and unit != self._last_unit)
        self._last_unit = unit
        liters = VolumeConverter.convert(value, unit, LITERS)
        events = self.model.on_meter(liters, now, baseline_only=baseline)
        self._need_baseline = False
        if events:
            self._log_events(events)
            self._update_notification()

    def _report_unit_problem(self, unit: str) -> None:
        if self._unit_problem == unit:
            return
        self._unit_problem = unit
        _LOGGER.warning(
            "Einheit %r von %s ist keine bekannte Volumeneinheit; der Zählerstand wird nicht gezählt", unit, self.water_entity
        )
        prefix = f"component.{DOMAIN}.issues.unknown_unit"
        placeholders = {"name": self.entry.title, "entity": self.water_entity, "unit": unit}
        title = self._issue_texts.get(f"{prefix}.title", "Unknown unit of the water meter")
        message = self._issue_texts.get(
            f"{prefix}.description", "The unit {unit} of {entity} is not a known volume unit."
        )
        persistent_notification.async_create(
            self.hass,
            message.format(**placeholders),
            title=title.format(**placeholders),
            notification_id=unit_notification_id(self.entry.entry_id),
        )

    def _clear_unit_problem(self) -> None:
        if self._unit_problem is not None:
            self._unit_problem = None
            persistent_notification.async_dismiss(self.hass, unit_notification_id(self.entry.entry_id))

    @callback
    def _handle_state_event(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        self._process_state(new_state, dt_util.as_local(new_state.last_updated))
        self._publish()
        self._save_later()

    @callback
    def _handle_window_end(self, now: datetime) -> None:
        """Planmäßige Auswertung kurz nach dem Ende des Zeitfensters; danach den nächsten Termin setzen."""
        self._unsub_timer = None
        local = dt_util.as_local(now)
        events = self.model.evaluate_pending(local, scheduled=True)
        if events:
            self._log_events(events)
        self._update_notification()
        self._publish()
        self._save_later()
        self._schedule_evaluation(local)

    def _log_events(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            if event["type"] == "regeneration":
                _LOGGER.info(
                    "Regeneration erkannt (%s: %.1f L im Zeitfenster), Restbestand %s Regenerationen",
                    event["date"],
                    event["usage_l"],
                    self.model.remaining_regens,
                )
            elif event["type"] == "window_closed":
                _LOGGER.debug("Zeitfenster %s abgeschlossen: %.1f L", event["date"], event["usage_l"])

    # ------------------------------------------------------------------ Eingriffe (Tasten und Dienste)
    async def async_refill(self, kg: float | None) -> None:
        """Nachfüllen bestätigen: die Menge (kg) ist Pflicht und wird zum Bestand addiert."""
        if kg is None or not float(kg) > 0:
            raise service_error("refill_amount_required")
        added = self.model.refill(dt_util.now(), float(kg))
        if added < float(kg) - 1e-6:
            _LOGGER.warning(
                "Nachgefüllt: %.2f kg, im Behälter ist aber nur Platz für %.2f kg; der Bestand wurde auf die Behältergröße begrenzt",
                float(kg),
                added,
            )
        self.refill_input_kg = 0.0
        self._after_manual_change()

    async def async_refill_full(self) -> None:
        """Behälter ist voll: Bestand auf die Behältergröße setzen (ohne Mengeneingabe)."""
        self.model.refill_full(dt_util.now())
        self.refill_input_kg = 0.0
        self._after_manual_change()

    def set_refill_input(self, kg: float) -> None:
        self.refill_input_kg = max(0.0, float(kg))
        self._publish()

    async def async_set_stock(self, kg: float) -> None:
        self.model.set_stock(kg)
        self._after_manual_change()

    @staticmethod
    def _past_local(at: datetime) -> datetime:
        """Zeitpunkt als Ortszeit (ohne Zeitzone: Ortszeit von Home Assistant); Zukunft wird abgelehnt."""
        if at.tzinfo is None:
            at = at.replace(tzinfo=dt_util.get_default_time_zone())
        at = dt_util.as_local(at)
        if at > dt_util.now():
            raise service_error("datetime_in_future")
        return at

    async def async_add_regeneration(self, count: int = 1, at: datetime | None = None) -> None:
        """Regeneration(en) nachtragen; at = Zeitpunkt (Standard: jetzt, nicht in der Zukunft)."""
        when = dt_util.now() if at is None else self._past_local(at)
        self.model.add_manual_regeneration(when, count)
        self._after_manual_change()

    async def async_set_last_regeneration(self, at: datetime) -> None:
        """Zeitpunkt der letzten Regeneration korrigieren (ohne Zeitzone: Ortszeit von Home Assistant)."""
        when = self._past_local(at)
        self.model.set_last_regeneration(when, dt_util.now())
        self._after_manual_change()

    async def async_set_regens_since_refill(self, count: int) -> None:
        """Bekannte Regenerationen seit dem letzten Füllen setzen; der Salzbestand ändert sich relativ dazu."""
        try:
            self.model.set_regens_since_refill(count)
        except ValueError as err:
            raise service_error("negative_count") from err
        self._after_manual_change()

    def _after_manual_change(self) -> None:
        self._update_notification()
        self._publish()
        self._save_later()

    # ------------------------------------------------------------------ Benachrichtigung
    def _update_notification(self) -> None:
        lang = "de" if str(self.hass.config.language).lower().startswith("de") else "en"
        texts = MESSAGES[lang]
        self._update_overdue_notification(texts)
        nid = notification_id(self.entry.entry_id)
        if not self.model.needs_refill:
            persistent_notification.async_dismiss(self.hass, nid)
            return
        left = self.model.remaining_regens
        persistent_notification.async_create(
            self.hass,
            texts["message"].format(
                name=self.entry.title,
                left=left,
                unit=texts["one"] if left == 1 else texts["many"],
                stock=f"{self.model.state.stock_kg:.1f}",
                capacity=f"{self.settings.capacity_kg:.1f}",
            ),
            title=texts["title"],
            notification_id=nid,
        )

    def _update_overdue_notification(self, texts: dict[str, Any]) -> None:
        nid = overdue_notification_id(self.entry.entry_id)
        now = dt_util.now()
        if not self.model.regen_overdue(now):
            persistent_notification.async_dismiss(self.hass, nid)
            return
        last = self.model.state.last_regen_at
        due = self.model.next_regen_due(now.tzinfo)
        persistent_notification.async_create(
            self.hass,
            texts["overdue_message"].format(
                name=self.entry.title,
                last=dt_util.as_local(last).strftime("%d.%m.%Y %H:%M") if last else "–",
                due=due.strftime("%d.%m.%Y") if due else "–",
            ),
            title=texts["overdue_title"],
            notification_id=nid,
        )

    # ------------------------------------------------------------------ Daten für die Entitäten
    def snapshot(self) -> dict[str, Any]:
        m, s = self.model, self.model.state
        return {
            "total_regenerations": s.total_regens,
            "regenerations_since_refill": s.regens_since_refill,
            "salt_stock_kg": round(s.stock_kg, 2),
            "salt_percent": round(m.salt_percent, 1),
            "regenerations_left": m.remaining_regens,
            "last_regeneration": s.last_regen_at,
            "last_refill": s.last_refill_at,
            "window_usage_l": round(s.window_usage_l, 1) if s.window_date is not None else None,
            "refill_needed": m.needs_refill,
            "next_regeneration_due": m.next_regen_due(dt_util.now().tzinfo),
            "regeneration_overdue": m.regen_overdue(dt_util.now()),
            "refill_input_kg": self.refill_input_kg,
            "history": [h.isoformat() for h in (s.history or [])],
            "capacity_kg": self.settings.capacity_kg,
            "per_regen_kg": self.settings.per_regen_kg,
            "warn_remaining": self.settings.warn_remaining,
        }

    def _publish(self) -> None:
        self.coordinator.async_set_updated_data(self.snapshot())

    async def _async_update_data(self) -> dict[str, Any]:
        return self.snapshot()

    def _save_later(self) -> None:
        self._store.async_delay_save(self.model.to_dict, SAVE_DELAY)
