# Changelog

## 1.2.1

Korrekturen aus einem Code-Review.

- Zeitumstellung: Das Zeitfenster wird in echter Zeit gerechnet (Beginn zur eingestellten Ortszeit, Länge in echten
  Stunden, Vergleiche in UTC); die Auswertung läuft zum echten Fensterende + 1 Minute. Bisher war das Fenster 2 bis 3 Uhr
  in der Nacht der Umstellung auf Sommerzeit nur eine Minute lang, und bei der Umstellung auf Winterzeit wurde die
  doppelte Stunde zweimal erfasst. Jetzt: im März 03:00 bis 04:00 Uhr, im Oktober die erste Stunde 02:00 bis 03:00
  (Sommerzeit). Annahme: Die Uhr der Anlage stellt sich selbst um.
- „Regenerationen seit Nachfüllen korrigieren“ (und der Dienst `set_regenerations_since_refill`) ändert den Salzbestand
  jetzt relativ zur bisherigen Anzahl. Erneutes Bestätigen desselben Werts ändert nichts, Teil-Nachfüllungen gehen nicht
  mehr verloren.
- Einheiten des Wasserzählers über die Umrechnung von Home Assistant: zusätzlich gal, ft³, CCF. Unbekannte oder fehlende
  Einheit wird nicht mehr als Liter gewertet: Der Zählerstand wird nicht gezählt, es erscheint die Meldung „Einheit des
  Wasserzählers unbekannt“. Wechselt die Einheit, wird nur ein neuer Bezugswert gesetzt.
- Meldung „Regeneration überfällig“: Text nennt den Fälligkeitstag statt „seit mehr als 7 Tagen“.
- `add_regeneration` hat ein optionales Feld `datetime` (Zeitpunkt der Regeneration, Standard jetzt). Ein älterer
  Zeitpunkt verschiebt die letzte Regeneration nicht zurück.
- Fehlermeldungen der Dienste sind übersetzt (Deutsch/Englisch).
- Beim Entladen oder Deaktivieren werden die Meldungen entfernt (beim Laden bei Bedarf neu angelegt).
- `homeassistant.update_entity` schreibt keinen Fehler mehr ins Protokoll.
- Scheitert die Einrichtung der Plattformen, werden Zeitplan und Listener wieder abgemeldet.
- Dienst `refill`: kleinste Menge in der Oberfläche 0,01 kg (vorher 0,5 kg), wie im Schema „größer als 0“.
- Einstellungen: Beschreibungen im Optionsdialog, ungenutzte Fehlermeldung entfernt.
- Gespeicherter Zustand wird robuster geladen (fehlende oder als Text gespeicherte Werte).
- Tests mit echtem Home Assistant (2024.12 und 2026.2) in der CI; das Release wird erst nach erfolgreicher Validierung
  angelegt.

## 1.2.0

Zustand von Hand eintragen, z. B. beim Einrichten mitten in einer Füllung.

- Neue Eingabe „Letzte Regeneration korrigieren“ (Datum und Uhrzeit, unter „Konfiguration“ am Gerät) und Dienst
  `water_softener_refill_sensor.set_last_regeneration`: setzt den Zeitpunkt der letzten Regeneration. Danach richten sich
  „Nächste Regeneration spätestens“ und „Regeneration überfällig“. Es wird keine Regeneration gezählt; Zeitpunkte in der
  Zukunft werden abgelehnt.
- Neue Eingabe „Regenerationen seit Nachfüllen korrigieren“ (Zahl, unter „Konfiguration“) und Dienst
  `water_softener_refill_sensor.set_regenerations_since_refill`: setzt die bekannten Regenerationen seit dem letzten Füllen
  bis voll. Der Salzbestand wird daraus berechnet (Behältergröße − Anzahl × Salzverbrauch pro Regeneration), die Meldung
  „Salz nachfüllen“ passt sich sofort an. Der Gesamtzähler wird bei Bedarf auf mindestens diese Anzahl angehoben.
- Mit einem echten Home Assistant (2026.2) geprüft.

## 1.1.1

- Fehler behoben: Beim Hinzufügen der Integration brach der Einrichtungsdialog mit „Der Konfigurationsfluss konnte nicht
  geladen werden: 400: Bad Request“ ab. Ursache: Das Feld „Warnung bei Restbestand von“ übergab Home Assistant eine leere
  Einheit (`unit_of_measurement: None`), die Home Assistant ablehnt. Felder ohne Einheit übergeben jetzt keine Einheit mehr.
- Einrichtung, Optionen, Entitäten, Tasten und Dienste wurden zusätzlich mit einem echten Home Assistant (2026.2) geprüft.
- Neuer Test, der leere Einheiten im Formular erkennt.

## 1.1.0

Die Integration heißt jetzt „Water Softener Refill Sensor“ (Domain `water_softener_refill_sensor`, Repository
`BeGiBue/water-softener-refill-sensor`). Das Quittieren der Salzmeldung verlangt jetzt die nachgefüllte Menge.
Weil sich die Domain geändert hat, werden Einträge und gespeicherte Daten der Version 1.0.0 nicht übernommen: Die
Integration muss neu eingerichtet werden.

- Dienst `water_softener_refill_sensor.refill`: `kg` ist Pflicht (größer als 0). Die Menge wird zum Bestand addiert, höchstens bis zur
  Behältergröße. Ohne Menge gibt es eine Fehlermeldung; „Behälter voll“ ohne Angabe entfällt.
- Neue Eingabe „Nachgefüllte Salzmenge“ (Zahlenfeld in kg). Die Taste „Salz nachgefüllt“ bestätigt mit dieser Menge; bei
  Menge 0 wird nicht quittiert. Nach dem Bestätigen springt die Eingabe auf 0 zurück.
- Die Meldung endet erst, wenn der Bestand nach dem Nachfüllen wieder über der Warnschwelle liegt; reicht die Menge nicht,
  bleibt sie mit dem neuen Stand bestehen.
- „Regenerationen seit Nachfüllen“ wird nur zurückgesetzt, wenn der Behälter nach dem Nachfüllen voll ist; bei einer
  Teilmenge zählt er weiter.
- Neue Taste „Behälter voll“: setzt den Bestand mit einem Knopfdruck auf voll, setzt den Zähler seit Nachfüllen zurück und
  beendet die Meldung, ohne Mengeneingabe.
- Standardwert Salzverbrauch pro Regeneration: 1,28 kg (Schrittweite im Formular 0,01 kg).
- 7-Tage-Regel der Anlage (Hygieneregeneration): neuer Sensor „Nächste Regeneration spätestens“, Binärsensor und Meldung
  „Regeneration überfällig“, wenn am Fälligkeitstag keine Regeneration erkannt wurde (Hinweis auf Zählerausfall oder
  Störung). Die Regeneration wird dabei nicht automatisch gezählt; Nachtragen mit `water_softener_refill_sensor.add_regeneration`.
- Meldungstext und Übersetzungen angepasst.

## 1.0.0

Erstes Release der Home-Assistant-Integration „Water Softener Refill Sensor“.

- Zählt die Regenerationen einer Enthärtungsanlage über den Wasserzähler: Wird im Zeitfenster (Standard 2 bis 3 Uhr) mehr
  Wasser als der Schwellwert (Standard 45 Liter) verbraucht, zählt das als eine Regeneration.
- Rechnerischer Salzbestand aus Behältergröße (kg) und Salzverbrauch pro Regeneration (kg); Anzeige in kg, in Prozent und
  als Restbestand in Regenerationen.
- Meldung in Home Assistant, sobald der Restbestand die einstellbare Warnschwelle (Standard 3 Regenerationen) erreicht.
  Sie bleibt bestehen, bis das Nachfüllen bestätigt wird (Taste „Salz nachgefüllt“ oder Dienst `water_softener_refill_sensor.refill`).
- Einrichtung und Änderung aller Werte über die Oberfläche (Konfigurations- und Optionsfluss), Deutsch und Englisch.
- Entitäten: Regenerationen gesamt und seit dem Nachfüllen, Salzbestand, Salzfüllstand, Restbestand, letzte Regeneration,
  letztes Nachfüllen, Verbrauch im Zeitfenster, „Salz nachfüllen“ (Problem) und die Bestätigungstaste.
- Dienste: `refill`, `set_salt_stock`, `add_regeneration`.
- Zustand bleibt über Neustarts erhalten; ein während eines Neustarts beendetes Zeitfenster wird nachträglich ausgewertet.
