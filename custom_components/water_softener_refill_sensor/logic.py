"""Reine Logik der Regenerationserkennung und der Salzbestandsrechnung.

Dieses Modul hat bewusst keine Home-Assistant-Abhängigkeiten, damit es ohne Home Assistant getestet werden kann
(siehe tests/test_logic.py). Alle Zeitangaben sind zeitzonenbehaftete datetime-Objekte (in Home Assistant: Ortszeit).

Funktionsweise
--------------
* Ein Wasserzähler (kumulierter Stand in Litern) wird überwacht. Im Zeitfenster (Standard 02:00 bis 03:00 Uhr) werden
  alle Zuwächse des Zählerstands addiert.
* Eine Minute nach Ende des Fensters wird ausgewertet: Ist der Verbrauch im Fenster größer als der Schwellwert
  (Standard 45 Liter), zählt das als eine Regeneration.
* Jede Regeneration verbraucht eine einstellbare Menge Salz. Der Salzbestand ist rein rechnerisch. Beim Nachfüllen
  muss die nachgefüllte Menge (kg) angegeben werden; sie wird zum Bestand addiert (höchstens bis voll).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

# Das Fenster wird erst eine Minute nach seinem Ende ausgewertet, damit späte Zählerwerte noch erfasst werden.
EVAL_DELAY = timedelta(minutes=1)
# Die Anlage regeneriert spätestens 7 Tage nach der letzten Regeneration (Hygiene), auch ohne Wasserverbrauch.
HYGIENE_DAYS = 7
HISTORY_LENGTH = 10


@dataclass
class Settings:
    """Einstellungen der Enthärtungsanlage."""

    capacity_kg: float
    per_regen_kg: float
    threshold_l: float = 45.0
    start_hour: int = 2
    end_hour: int = 3
    warn_remaining: int = 3


@dataclass
class State:
    """Veränderlicher Zustand (wird persistent gespeichert)."""

    stock_kg: float
    total_regens: int = 0
    regens_since_refill: int = 0
    last_value_l: float | None = None
    window_date: date | None = None
    window_usage_l: float = 0.0
    window_crossed_at: datetime | None = None
    evaluated_date: date | None = None
    last_regen_at: datetime | None = None
    last_refill_at: datetime | None = None
    history: list[datetime] | None = None

    def __post_init__(self) -> None:
        if self.history is None:
            self.history = []


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class SoftenerModel:
    """Rechenmodell: Regenerationen zählen und Salzbestand führen."""

    def __init__(self, settings: Settings, state: State | None = None, initial_stock_kg: float | None = None) -> None:
        self.settings = settings
        if state is None:
            stock = settings.capacity_kg if initial_stock_kg is None else initial_stock_kg
            state = State(stock_kg=self._clamp(stock))
        self.state = state
        # Falls die Behältergröße verkleinert wurde, darf der Bestand sie nicht übersteigen
        self.state.stock_kg = self._clamp(self.state.stock_kg)

    # ------------------------------------------------------------------ Hilfsfunktionen
    def _clamp(self, kg: float) -> float:
        return max(0.0, min(float(kg), float(self.settings.capacity_kg)))

    def window_start(self, day: date, tz: Any) -> datetime:
        return datetime.combine(day, time(self.settings.start_hour, 0), tzinfo=tz)

    def window_end(self, day: date, tz: Any) -> datetime:
        """Ende des Erfassungsfensters = Auswertezeitpunkt (Ende des Zeitfensters plus Nachlauf)."""
        return datetime.combine(day, time(self.settings.end_hour, 0), tzinfo=tz) + EVAL_DELAY

    def in_window(self, now: datetime) -> bool:
        day = now.date()
        return self.window_start(day, now.tzinfo) <= now < self.window_end(day, now.tzinfo)

    # ------------------------------------------------------------------ Kennzahlen
    @property
    def remaining_regens(self) -> int:
        """Rechnerischer Restbestand in Regenerationen (abgerundet)."""
        if self.settings.per_regen_kg <= 0:
            return 0
        return int(math.floor(self.state.stock_kg / self.settings.per_regen_kg + 1e-9))

    @property
    def salt_percent(self) -> float:
        if self.settings.capacity_kg <= 0:
            return 0.0
        return 100.0 * self.state.stock_kg / self.settings.capacity_kg

    @property
    def needs_refill(self) -> bool:
        return self.remaining_regens <= self.settings.warn_remaining

    # ------------------------------------------------------------------ 7-Tage-Regel (Hygieneregeneration)
    def next_regen_due(self, tz: Any) -> datetime | None:
        """Spätestens fälliger Zeitpunkt der nächsten Regeneration: Beginn des Zeitfensters 7 Tage nach der letzten."""
        last = self.state.last_regen_at
        if last is None:
            return None
        due_day = last.astimezone(tz).date() + timedelta(days=HYGIENE_DAYS)
        return self.window_start(due_day, tz)

    def regen_overdue(self, now: datetime) -> bool:
        """Wahr, wenn das Zeitfenster am Fälligkeitstag ausgewertet wurde und keine Regeneration erkannt wurde.

        Hinweis auf einen verpassten Zählerwert (Wasserzähler ausgefallen) oder auf eine Störung der Anlage.
        """
        due = self.next_regen_due(now.tzinfo)
        if due is None:
            return False
        return now >= self.window_end(due.date(), now.tzinfo)

    # ------------------------------------------------------------------ Zählerstand verarbeiten
    def on_meter(self, value_l: float, now: datetime, baseline_only: bool = False) -> list[dict[str, Any]]:
        """Neuen Zählerstand (in Litern) verarbeiten.

        baseline_only=True setzt nur den Bezugswert (z. B. nach einem Neustart oder wenn der Zähler zuvor
        nicht verfügbar war), ohne einen Zuwachs zu zählen. So werden Lücken in den Daten nicht fälschlich
        als Verbrauch im Zeitfenster gewertet.
        """
        events = self.evaluate_pending(now)
        st = self.state
        prev = st.last_value_l
        st.last_value_l = value_l
        if baseline_only or prev is None:
            return events
        delta = value_l - prev
        if delta <= 0:  # unverändert, oder Zähler zurückgesetzt/getauscht (negativ): nichts zählen
            return events
        if self.in_window(now):
            day = now.date()
            if st.window_date != day:  # neues Fenster beginnt
                st.window_date = day
                st.window_usage_l = 0.0
                st.window_crossed_at = None
            st.window_usage_l += delta
            if st.window_crossed_at is None and st.window_usage_l > self.settings.threshold_l:
                st.window_crossed_at = now
        return events

    # ------------------------------------------------------------------ Auswertung
    def evaluate_pending(self, now: datetime, scheduled: bool = False) -> list[dict[str, Any]]:
        """Ein beendetes, noch nicht ausgewertetes Zeitfenster abschließen.

        scheduled=True: Aufruf zum planmäßigen Ende des Fensters. Gab es im Fenster gar keinen Verbrauch
        (kein Zählerupdate), wird "0 Liter" festgehalten.
        """
        st = self.state
        today = now.date()
        wd = st.window_date
        if wd is not None and st.evaluated_date != wd:
            if now >= self.window_end(wd, now.tzinfo):
                return self._finalize(wd, now.tzinfo)
            return []
        if scheduled and st.evaluated_date != today and now >= self.window_end(today, now.tzinfo):
            st.window_date = today
            st.window_usage_l = 0.0
            st.window_crossed_at = None
            st.evaluated_date = today
            return [{"type": "window_closed", "date": today, "usage_l": 0.0}]
        return []

    def _finalize(self, day: date, tz: Any) -> list[dict[str, Any]]:
        st = self.state
        st.evaluated_date = day
        usage = st.window_usage_l
        events: list[dict[str, Any]] = [{"type": "window_closed", "date": day, "usage_l": usage}]
        if usage > self.settings.threshold_l:
            at = st.window_crossed_at or self.window_end(day, tz)
            self._register(at)
            events.append({"type": "regeneration", "date": day, "at": at, "usage_l": usage, "manual": False})
        return events

    def _register(self, at: datetime) -> None:
        st = self.state
        st.total_regens += 1
        st.regens_since_refill += 1
        st.stock_kg = self._clamp(round(st.stock_kg - self.settings.per_regen_kg, 4))
        st.last_regen_at = at
        st.history = ([at] + (st.history or []))[:HISTORY_LENGTH]

    # ------------------------------------------------------------------ Eingriffe von Hand
    def add_manual_regeneration(self, at: datetime, count: int = 1) -> None:
        """Eine (nicht erkannte) Regeneration von Hand nachtragen."""
        for _ in range(max(0, int(count))):
            self._register(at)

    def refill(self, now: datetime, kg: float) -> float:
        """Salz nachgefüllt: die Menge (kg, größer als 0) wird zum Bestand addiert, höchstens bis zur Behältergröße.

        Der Zähler „Regenerationen seit Nachfüllen“ wird nur zurückgesetzt, wenn der Behälter danach voll ist.
        Gibt die Menge zurück, die tatsächlich im Bestand angekommen ist (kleiner als kg, wenn der Behälter überfüllt wäre).
        """
        if kg is None or not float(kg) > 0:
            raise ValueError("Die nachgefüllte Menge muss größer als 0 kg sein.")
        st = self.state
        before = st.stock_kg
        st.stock_kg = self._clamp(round(before + float(kg), 4))
        if st.stock_kg >= float(self.settings.capacity_kg) - 1e-9:
            st.regens_since_refill = 0
        st.last_refill_at = now
        return round(st.stock_kg - before, 4)

    def refill_full(self, now: datetime) -> float:
        """Behälter ist voll: Bestand = Behältergröße, Zähler seit Nachfüllen zurücksetzen.

        Gibt die Menge zurück, die dem rechnerischen Bestand hinzugefügt wurde.
        """
        st = self.state
        before = st.stock_kg
        st.stock_kg = self._clamp(self.settings.capacity_kg)
        st.regens_since_refill = 0
        st.last_refill_at = now
        return round(st.stock_kg - before, 4)

    def set_stock(self, kg: float) -> None:
        self.state.stock_kg = self._clamp(kg)

    # ------------------------------------------------------------------ Speichern / Laden
    def to_dict(self) -> dict[str, Any]:
        s = self.state
        return {
            "stock_kg": s.stock_kg,
            "total_regens": s.total_regens,
            "regens_since_refill": s.regens_since_refill,
            "last_value_l": s.last_value_l,
            "window_date": s.window_date.isoformat() if s.window_date else None,
            "window_usage_l": s.window_usage_l,
            "window_crossed_at": s.window_crossed_at.isoformat() if s.window_crossed_at else None,
            "evaluated_date": s.evaluated_date.isoformat() if s.evaluated_date else None,
            "last_regen_at": s.last_regen_at.isoformat() if s.last_regen_at else None,
            "last_refill_at": s.last_refill_at.isoformat() if s.last_refill_at else None,
            "history": [h.isoformat() for h in (s.history or [])],
        }

    @classmethod
    def from_dict(cls, settings: Settings, data: dict[str, Any]) -> "SoftenerModel":
        state = State(
            stock_kg=float(data.get("stock_kg", settings.capacity_kg)),
            total_regens=int(data.get("total_regens", 0)),
            regens_since_refill=int(data.get("regens_since_refill", 0)),
            last_value_l=data.get("last_value_l"),
            window_date=_d(data.get("window_date")),
            window_usage_l=float(data.get("window_usage_l", 0.0)),
            window_crossed_at=_dt(data.get("window_crossed_at")),
            evaluated_date=_d(data.get("evaluated_date")),
            last_regen_at=_dt(data.get("last_regen_at")),
            last_refill_at=_dt(data.get("last_refill_at")),
            history=[_dt(h) for h in data.get("history", []) if h],
        )
        return cls(settings, state)
