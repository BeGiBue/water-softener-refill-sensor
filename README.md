# Water Softener Refill Sensor für Home Assistant

Eine Home-Assistant-Integration, die zählt, **wie oft eine Enthärtungsanlage regeneriert hat**, und den **Salzbestand**
mitrechnet. Sie meldet sich, wenn bald Salz nachgefüllt werden muss.

Sie ergänzt die Karte [Heizungskeller Schema](https://github.com/BeGiBue/heizungskeller-schema), kann aber auch ganz
ohne sie genutzt werden.

## So funktioniert es

- **Regeneration erkennen:** Die Anlage regeneriert nachts, zum Beispiel zwischen 2 und 3 Uhr, und verbraucht dabei
  Wasser. Die Integration überwacht dazu den **Wasserzähler** (kumulierter Stand). Wird im Zeitfenster **mehr als der
  Schwellwert** (Standard 45 Liter) verbraucht, zählt das als **eine** Regeneration. Ausgewertet wird eine Minute nach
  Ende des Zeitfensters.
- **Salzbestand rechnen:** Du gibst ein, wie viel Kilogramm Salz in den Behälter passen und wie viel eine Regeneration
  verbraucht. Jede erkannte Regeneration verringert den rechnerischen Bestand.
- **Warnung:** Erreicht der rechnerische Restbestand die Warnschwelle (Standard **3 Regenerationen**), erscheint eine
  Meldung in Home Assistant. Sie bleibt bestehen, **bis du das Nachfüllen mit der nachgefüllten Menge in kg
  bestätigst**: Menge bei „Nachgefüllte Salzmenge“ eingeben und Taste „Salz nachgefüllt“ drücken, oder Dienst
  `water_softener_refill_sensor.refill` mit `kg` aufrufen. Die Menge wird zum Bestand addiert (höchstens bis voll). Liegt der Bestand danach
  noch unter der Warnschwelle, bleibt die Meldung bestehen. Ohne Mengenangabe lässt sich mit „Salz nachgefüllt“ nicht bestätigen. Ist der Behälter ganz voll, genügt die Taste
  „Behälter voll“.

## Verhalten der Anlage (Aqmos R2D2-32)

- Die Anlage misst den Wasserverbrauch und regeneriert in der Nacht nach dem Verbrauch ihrer Kapazität, bei den
  Standardeinstellungen zwischen 2 und 3 Uhr. Eine Regeneration verbraucht meist **52–53 Liter**; der Standard-Schwellwert
  von 45 Litern liegt deutlich darunter und erfasst sie sicher.
- Zusätzlich regeneriert sie **spätestens 7 Tage nach der letzten Regeneration** (Hygiene), auch ohne Wasserverbrauch.
  Die Integration zeigt dafür „Nächste Regeneration spätestens“ an. Wurde am Fälligkeitstag keine Regeneration erkannt
  (z. B. weil der Wasserzähler ausgefallen war), erscheinen die Meldung „Regeneration überfällig“ und der Binärsensor. Die
  Regeneration lässt sich mit `water_softener_refill_sensor.add_regeneration` nachtragen. Gezählt wird sie nicht von selbst.
- Der Behälter fasst nominell 25 kg Salz, eine Regeneration verbraucht 1,28 kg (Standardwerte). Weil meist nicht der
  ganze Sack auf einmal hineinpasst, wird in zwei Schritten nachgefüllt: Jede nachgefüllte Menge wird zum Bestand
  addiert. Erst wenn der Behälter danach voll ist (Bestand = Behältergröße, zu große Mengen werden abgeschnitten),
  springt „Regenerationen seit Nachfüllen“ auf 0.

## Installation

### Über HACS (empfohlen)

Mit einem Klick (über My Home Assistant öffnet sich das Repository direkt in HACS deiner Home-Assistant-Instanz):

[![In HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=BeGiBue&repository=water-softener-refill-sensor&category=integration)

Danach „Herunterladen“ wählen und Home Assistant **neu starten**.

Oder von Hand:

1. HACS öffnen → Menü (⋮) → **Benutzerdefinierte Repositories**.
2. URL `https://github.com/BeGiBue/water-softener-refill-sensor` eintragen, Kategorie **Integration** wählen.
3. „Water Softener Refill Sensor“ herunterladen und Home Assistant neu starten.

### Manuell

Den Ordner `custom_components/water_softener_refill_sensor` in dein `config/custom_components/` kopieren und Home Assistant neu starten.

## Einrichtung

*Einstellungen → Geräte & Dienste → Integration hinzufügen → „Water Softener Refill Sensor“.*

| Feld | Bedeutung | Standard |
|---|---|---|
| Name | Name des Geräts | Enthärtungsanlage |
| Wasserzähler | Sensor mit dem **kumulierten Zählerstand** in Litern oder m³ (z. B. der Sensor aus dem Energie-Dashboard) | – |
| Behältergröße | Wie viel kg Salz passen in den Behälter | 25 kg |
| Salzverbrauch pro Regeneration | kg Salz je Regeneration | 1,28 kg |
| Aktueller Salzbestand | Nur beim Einrichten, optional. Leer = Behälter voll | – |
| Schwellwert Wasserverbrauch | Verbrauch im Zeitfenster, ab dem eine Regeneration zählt (größer als) | 45 Liter |
| Zeitfenster von / bis | Wann die Regeneration stattfindet (volle Stunden, Ende nach Beginn) | 2 bis 3 Uhr |
| Warnung bei Restbestand von | Ab diesem Restbestand (in Regenerationen) erscheint die Meldung | 3 |

Alle Werte außer dem Namen und dem anfänglichen Bestand lassen sich später über **Konfigurieren** am Eintrag ändern.

**Mitten in einer Füllung starten:** Nach der Einrichtung am Gerät unter **Konfiguration** „Letzte Regeneration korrigieren“
(Datum vom Display der Anlage) und „Regenerationen seit Nachfüllen korrigieren“ (bisherige Regenerationen seit dem letzten
Füllen) eintragen. Der Salzbestand wird dann aus der Anzahl berechnet.

## Entitäten

Die Entitäten gehören zu einem Gerät mit dem eingestellten Namen (die genauen Entitäts-IDs hängen von Name und Sprache ab).

| Entität | Beschreibung |
|---|---|
| Regenerationen gesamt | Zähler aller erkannten Regenerationen |
| Regenerationen seit Nachfüllen | Zähler seit dem letzten Füllen bis voll; wird nur zurückgesetzt, wenn der Behälter nach dem Nachfüllen voll ist |
| Salzbestand | Rechnerischer Bestand in kg |
| Salzfüllstand | Rechnerischer Füllstand in Prozent |
| Restbestand Regenerationen | Für wie viele Regenerationen das Salz noch reicht (abgerundet) |
| Letzte Regeneration | Zeitpunkt, an dem der Schwellwert überschritten wurde (Attribut `history`: letzte 10) |
| Nächste Regeneration spätestens | 7 Tage nach der letzten Regeneration, Beginn des Zeitfensters (Hygieneregeneration) |
| Letztes Nachfüllen | Zeitpunkt der letzten Bestätigung (Diagnose) |
| Verbrauch im Zeitfenster | Wasserverbrauch des letzten bzw. laufenden Zeitfensters (Diagnose) |
| Salz nachfüllen | Binärsensor „Problem“: an, solange der Restbestand die Warnschwelle erreicht hat |
| Regeneration überfällig | Binärsensor „Problem“: an, wenn seit mehr als 7 Tagen keine Regeneration erkannt wurde |
| Nachgefüllte Salzmenge | Eingabe in kg (Zahlenfeld): die Menge, die du nachgefüllt hast; wird nach dem Bestätigen auf 0 zurückgesetzt |
| Behälter voll | Taste: setzt den Salzbestand mit einem Knopfdruck auf voll (Behältergröße), setzt „Regenerationen seit Nachfüllen“ auf 0 und beendet die Meldung; keine Mengeneingabe nötig |
| Salz nachgefüllt | Taste: bestätigt das Nachfüllen mit der eingegebenen Menge, addiert sie zum Bestand und beendet die Meldung, sobald der Bestand über der Warnschwelle liegt. Bei Menge 0 passiert nichts (Fehlermeldung). |
| Letzte Regeneration korrigieren | Eingabe Datum und Uhrzeit (Konfiguration): Zeitpunkt der letzten Regeneration von Hand setzen, z. B. vom Display der Anlage. Bestimmt „Nächste Regeneration spätestens“ und „Regeneration überfällig“; zählt keine Regeneration |
| Regenerationen seit Nachfüllen korrigieren | Eingabe Zahl (Konfiguration): bekannte Regenerationen seit dem letzten Füllen bis voll. Der Salzbestand wird daraus berechnet (Behältergröße − Anzahl × Salzverbrauch pro Regeneration) |

## Dienste

| Dienst | Zweck |
|---|---|
| `water_softener_refill_sensor.refill` | Nachfüllen bestätigen. `kg` (Pflicht, größer als 0): nachgefüllte Menge, wird zum Bestand addiert (höchstens bis voll). |
| `water_softener_refill_sensor.set_salt_stock` | Rechnerischen Bestand auf einen Wert in kg setzen (z. B. nach Kontrolle des Behälters). |
| `water_softener_refill_sensor.add_regeneration` | Eine nicht erkannte Regeneration von Hand nachtragen (`count`). |
| `water_softener_refill_sensor.set_last_regeneration` | Zeitpunkt der letzten Regeneration setzen (`datetime`, nicht in der Zukunft). Zähler und Bestand bleiben unverändert. |
| `water_softener_refill_sensor.set_regenerations_since_refill` | Bekannte Regenerationen seit dem letzten Füllen bis voll setzen (`count`); der Salzbestand wird daraus berechnet. |

Sind mehrere Anlagen eingerichtet, wird zusätzlich der Eintrag (`config_entry`) angegeben.

## Anbindung an die Karte „Heizungskeller Schema“

Die Karte hat eine Tafel „Enthärtungsanlage“ mit zwei Zeilen. Im Karteneditor, Bereich **Enthärtungsanlage**, wählst du:

- **Regeneration** → z. B. „Regenerationen gesamt“ oder „Restbestand Regenerationen“
- **Salz** → „Salzfüllstand“ (Prozent)

## Hinweise und Grenzen

- Die Erkennung ist eine **Näherung** über den Wasserverbrauch: Wird nachts im Zeitfenster aus anderen Gründen viel Wasser
  verbraucht (mehr als der Schwellwert), kann das fälschlich als Regeneration zählen. Eine nicht erkannte Regeneration
  lässt sich mit `water_softener_refill_sensor.add_regeneration` nachtragen, ein falscher Bestand mit `water_softener_refill_sensor.set_salt_stock`.
- Der Wasserzähler sollte seinen Stand **laufend** aktualisieren (nicht nur alle Stunde), damit der Verbrauch im
  Zeitfenster erfasst wird. Nach einem Neustart oder wenn der Zähler zwischenzeitlich „nicht verfügbar“ war, wird nur ein
  neuer Bezugswert gesetzt; der Verbrauch dazwischen wird bewusst nicht gezählt.
- Der Salzverbrauch pro Regeneration wird als **konstant** angenommen. Der Bestand ist rein rechnerisch und ersetzt
  keinen Blick in den Salzbehälter.
- Das Zeitfenster darf nicht über Mitternacht gehen (Beginn muss vor dem Ende liegen).
- Zustand (Zähler, Bestand) wird gespeichert und bleibt über Neustarts erhalten.
- Benötigt Home Assistant 2024.12 oder neuer.

## Entwicklung

Die Berechnung steckt in `custom_components/water_softener_refill_sensor/logic.py` und kommt ohne Home Assistant aus. Tests:

```bash
python3 -m unittest discover -s tests -v
```

`tests/test_logic.py` prüft die Berechnung, `tests/test_integration_smoke.py` spielt mit Attrappen der Home-Assistant-
Schnittstellen eine ganze Nacht durch (Zählerstände, Regeneration, Meldung, Bestätigung, Neustart, Dienste). Die Attrappen
prüfen den eigenen Code, **nicht** die Kompatibilität zur echten Home-Assistant-API; ein Test in einer echten
Home-Assistant-Instanz ist deshalb nötig. Arbeitsanweisungen für Claude Code stehen in `CLAUDE.md`.
