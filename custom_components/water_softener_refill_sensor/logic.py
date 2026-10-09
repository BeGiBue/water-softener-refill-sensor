"""Reine Logik der Regenerationserkennung und der Salzbestandsrechnung.

Dieses Modul hat bewusst keine Home-Assistant-Abhängigkeiten, damit es ohne Home Assistant getestet werden kann
(siehe tests/test_logic.py). Alle Zeitangaben sind zeitzonenbehaftete datetime-Objekte (in Home Assistant: Ortszeit).

Funktionsweise
--------------
* Ein Wasserzähler (kumulierter Stand in Litern) wird überwacht. Im Zeitfenster (Standard 02:00 bis 03:00 Uhr) werden
  alle Zuwächse des Zählerstands addiert.
* Eine Minute nach Ende des Fensters wird ausgewertet: Ist der Verbrauch im Fenster größer als der Schwellwert
  (Standard 45 Liter), zählt das als eine Regeneration. Erfasst wird bewusst bis zu diesem Auswertezeitpunkt, also
  einschließlich der Minute nach dem Fensterende, damit verspätet gemeldete Zählerwerte noch zählen.
* Zeitfenster in echter Zeit: Der Beginn ist die eingestellte Stunde in Ortszeit, die Länge (Ende − Beginn) wird in
  echten Stunden gerechnet, alle Vergleiche laufen in UTC. Annahme: Die Uhr der Anlage folgt der Ortszeit und stellt
  bei Sommer-/Winterzeit selbst um. Folgen bei der Umstellung (Europe/Berlin, Fenster 2–3 Uhr):
  - Oktober: Fenster 02:00 MESZ bis 02:00 MEZ (die erste der beiden Stunden), keine Doppelerfassung.
  - März: 02:00 gibt es nicht, der Beginn rückt auf 03:00 MESZ vor, Fenster 03:00 bis 04:00 MESZ.
* Jede Regeneration verbraucht eine einstellbare Menge Salz. Der Salzbestand ist rein rechnerisch. Beim Nachfüllen
  muss die nachgefüllte Menge (kg) angegeben werden; sie wird zum Bestand addiert (höchstens bis voll).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
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


def _utc(value: datetime) -> datetime:
    """Zeitpunkt in UTC: Vergleiche gleicher Zeitzone liefen sonst nach Wanduhrzeit (Fehler bei der Zeitumstellung)."""
    return value.astimezone(timezone.utc)


def _dt(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _d(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _float(value: Any, default: float | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


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
        """Beginn des Fensters am Tag day (Ortszeit tz).

        Doppelte Ortszeit (Oktober): die erste (fold=0). Nicht existierende Ortszeit (März): fold=0 rechnet mit dem
        Versatz vor der Umstellung, der Beginn rückt damit um die Lücke nach vorn (02:00 → 03:00 MESZ).
        """
        local = datetime.combine(day, time(self.settings.start_hour, 0), tzinfo=tz)
        return _utc(local).astimezone(tz)

    def window_end(self, day: date, tz: Any) -> datetime:
        """Ende des Erfassungsfensters = Auswertezeitpunkt: Beginn + Fensterlänge in echten Stunden + Nachlauf."""
        hours = self.settings.end_hour - self.settings.start_hour
        return (_utc(self.window_start(day, tz)) + timedelta(hours=hours) + EVAL_DELAY).astimezone(tz)

    def window_day(self, now: datetime) -> date | None:
        """Tag des Fensters, in dem now liegt (Erfassung einschließlich Nachlauf), sonst None."""
        today = now.date()
        for day in (today, today - timedelta(days=1)):
            if _utc(self.window_start(day, now.tzinfo)) <= _utc(now) < _utc(self.window_end(day, now.tzinfo)):
                return day
        return None

    def in_window(self, now: datetime) -> bool:
        return self.window_day(now) is not None

    def last_closed_day(self, now: datetime) -> date:
        """Tag des zuletzt beendeten Fensters (heute, wenn dessen Auswertezeitpunkt erreicht ist, sonst gestern)."""
        today = now.date()
        if _utc(now) >= _utc(self.window_end(today, now.tzinfo)):
            return today
        return today - timedelta(days=1)

    def next_evaluation(self, now: datetime) -> datetime:
        """Nächster Auswertezeitpunkt nach now (für den Zeitplan im Manager)."""
        today = now.date()
        for day in (today, today + timedelta(days=1), today + timedelta(days=2)):
            end = self.window_end(day, now.tzinfo)
            if _utc(end) > _utc(now):
                return end
        raise RuntimeError("kein Auswertezeitpunkt gefunden")  # pragma: no cover

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
        return _utc(now) >= _utc(self.window_end(due.date(), now.tzinfo))

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
        day = self.window_day(now)
        if day is not None:
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
        wd = st.window_date
        if wd is not None and st.evaluated_date != wd:
            if _utc(now) >= _utc(self.window_end(wd, now.tzinfo)):
                return self._finalize(wd, now.tzinfo)
            return []
        day = self.last_closed_day(now)
        if scheduled and (st.evaluated_date is None or st.evaluated_date < day):
            st.window_date = day
            st.window_usage_l = 0.0
            st.window_crossed_at = None
            st.evaluated_date = day
            return [{"type": "window_closed", "date": day, "usage_l": 0.0}]
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
        # Nachgetragene ältere Regenerationen verschieben die letzte (und damit die 7-Tage-Frist) nicht zurück
        if st.last_regen_at is None or _utc(at) >= _utc(st.last_regen_at):
            st.last_regen_at = at
        st.history = sorted([at] + (st.history or []), key=_utc, reverse=True)[:HISTORY_LENGTH]

    # ------------------------------------------------------------------ Eingriffe von Hand
    def add_manual_regeneration(self, at: datetime, count: int = 1) -> None:
        """Eine (nicht erkannte) Regeneration von Hand nachtragen (Zeitpunkt at; der Manager prüft „nicht in der Zukunft“)."""
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
        """Bestand setzen. „Regenerationen seit Nachfüllen“ bleibt unverändert: beide Werte sind unabhängig."""
        self.state.stock_kg = self._clamp(kg)

    def set_last_regeneration(self, at: datetime, now: datetime) -> None:
        """Zeitpunkt der letzten Regeneration von Hand setzen (bestimmt die 7-Tage-Regel). Nicht in der Zukunft."""
        if at > now:
            raise ValueError("Die letzte Regeneration darf nicht in der Zukunft liegen.")
        self.state.last_regen_at = at

    def set_regens_since_refill(self, count: int) -> None:
        """Bekannte Regenerationen seit dem letzten Füllen bis voll setzen.

        Der Bestand ändert sich relativ: um (bisherige Anzahl − count) × Salzverbrauch pro Regeneration, begrenzt auf
        0 bis Behältergröße. Erneutes Bestätigen desselben Werts ändert nichts, Teil-Nachfüllungen bleiben erhalten.
        Bei vollem Behälter und Zähler 0 (frisch eingerichtet) ergibt das Behältergröße − count × Verbrauch.
        Der Gesamtzähler wird bei Bedarf auf mindestens count angehoben.
        """
        count = int(count)
        if count < 0:
            raise ValueError("Die Anzahl der Regenerationen darf nicht negativ sein.")
        st = self.state
        delta = st.regens_since_refill - count
        st.regens_since_refill = count
        st.stock_kg = self._clamp(round(st.stock_kg + delta * self.settings.per_regen_kg, 4))
        st.total_regens = max(st.total_regens, count)

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
        """Gespeicherten Zustand laden. Fehlende oder unlesbare Felder bekommen Standardwerte (ältere Stände)."""
        state = State(
            stock_kg=_float(data.get("stock_kg"), float(settings.capacity_kg)),
            total_regens=_int(data.get("total_regens"), 0),
            regens_since_refill=_int(data.get("regens_since_refill"), 0),
            last_value_l=_float(data.get("last_value_l"), None),
            window_date=_d(data.get("window_date")),
            window_usage_l=_float(data.get("window_usage_l"), 0.0),
            window_crossed_at=_dt(data.get("window_crossed_at")),
            evaluated_date=_d(data.get("evaluated_date")),
            last_regen_at=_dt(data.get("last_regen_at")),
            last_refill_at=_dt(data.get("last_refill_at")),
            history=[h for h in (_dt(x) for x in (data.get("history") or [])) if h is not None],
        )
        return cls(settings, state)
