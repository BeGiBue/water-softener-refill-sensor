# Changelog

## 1.1.1

- Fehler behoben: Beim Hinzufügen der Integration brach der Einrichtungsdialog mit „Der Konfigurationsfluss konnte nicht
  geladen werden: 400: Bad Request“ ab. Ursache: Das Feld „Warnung bei Restbestand von“ übergab Home Assistant eine leere
  Einheit (`unit_of_measurement: None`), die Home Assistant ablehnt. Felder ohne Einheit übergeben jetzt keine Einheit mehr.
- Einrichtung, Optionen, Entitäten, Tasten und Dienste wurden zusätzlich mit einem echten Home Assistant (2026.2) geprüft.
- Neuer Test, der leere Einheiten im Formular erkennt.

## 1.1.0

Die Integration heißt jetzt „Water Softener Refill Sensor“ (Domain `water_softener_refill_sensor`, Repository
`BeGiBue/water-softener-refill-sensor`). Das Quittieren der Salzmeldung verlangt jetzt die nachgefüllte Menge.

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
