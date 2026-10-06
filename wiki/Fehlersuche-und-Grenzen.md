# Fehlersuche und Grenzen

## Schnelldiagnose

| Beobachtung | Mögliche Ursache | Was tun |
|---|---|---|
| **Nach der Nacht keine Regeneration gezählt**, obwohl die Anlage lief | Wasserzähler hat im Fenster nicht oder nur grob gemeldet; Zeitfenster passt nicht; Schwellwert zu hoch | Sensor „Verbrauch im Zeitfenster“ ansehen. Zeigt er 0 oder deutlich weniger als erwartet, melden zu wenige Zählerwerte oder das Fenster liegt falsch. Fehlende Regeneration mit `add_regeneration` nachtragen |
| **„Verbrauch im Zeitfenster“ ist leer** | Es wurde noch kein Fenster erfasst (frisch eingerichtet) | Nach der ersten Nacht erneut ansehen |
| **Regeneration gezählt, obwohl keine war** | Nachts wurde im Zeitfenster viel Wasser verbraucht (mehr als der Schwellwert) | Zeitfenster enger fassen, Schwellwert anheben (aber unter dem echten Regenerationsverbrauch lassen), Bestand mit `set_salt_stock` korrigieren |
| **„Regeneration überfällig“** | Wasserzähler war am Fälligkeitstag nicht verfügbar oder meldete nichts; oder die Anlage ist gestört | Prüfen, ob die Anlage regeneriert hat (Anzeige am Gerät). Wenn ja: `add_regeneration`. Wenn nein: Anlage prüfen |
| **Salzbestand weicht vom Behälter ab** | Verbrauch pro Regeneration nicht ganz konstant, nicht erkannte Regenerationen, Salz anders eingefüllt als eingetragen | Behälter ansehen, `set_salt_stock` |
| **Meldung „Salz nachfüllen“ kommt zu früh oder zu spät** | Warnschwelle oder Salzverbrauch pro Regeneration passt nicht | Beides unter *Konfigurieren* anpassen |
| **Taste „Salz nachgefüllt“ meldet einen Fehler** | Die Eingabe „Nachgefüllte Salzmenge“ steht auf 0 | Menge eintragen, dann Taste drücken. Oder „Behälter voll“ nutzen |
| **Nach dem Nachfüllen ist die Meldung noch da** | Restbestand liegt weiter bei oder unter der Warnschwelle | Siehe [Bedienung im Alltag](Bedienung-im-Alltag#die-meldung-bleibt-obwohl-ich-nachgefüllt-habe) |
| **Beim Einrichten: „Der Konfigurationsfluss konnte nicht geladen werden: 400: Bad Request“** | Fehler in Version 1.1.0: Ein Formularfeld ohne Einheit („Warnung bei Restbestand von“) gab Home Assistant eine leere Einheit | Auf Version 1.1.1 oder neuer aktualisieren (HACS) |
| **Integration lässt sich nicht einrichten oder startet nicht** | Fehler in der Anbindung | Protokoll auswerten (siehe unten) und als Issue melden |
| **Ich habe mitten in einer Füllung eingerichtet, und die Werte passen nicht** | Die Integration kennt die Vorgeschichte nicht | „Letzte Regeneration korrigieren“ und „Regenerationen seit Nachfüllen korrigieren“ eintragen (ab 1.2.0) |

## Ausführlicher protokollieren

Die Integration schreibt normalerweise nur das Wichtigste ins Protokoll (zum Beispiel jede erkannte Regeneration). Für die Fehlersuche schaltest du die Detailstufe ein, in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.water_softener_refill_sensor: debug
```

Danach Home Assistant neu starten (oder *Entwicklerwerkzeuge → Aktionen → `logger.set_level`* verwenden).

Das Protokoll findest du unter *Einstellungen → System → Protokolle*. Suche nach `water_softener_refill_sensor`.

Typische Zeilen:

| Zeile (sinngemäß) | Stufe | Bedeutung |
|---|---|---|
| „Regeneration erkannt (Datum: … L im Zeitfenster), Restbestand … Regenerationen“ | Info | Eine Regeneration wurde gezählt |
| „Zeitfenster … abgeschlossen: … L“ | Debug | Das Fenster wurde ausgewertet, auch ohne Regeneration |
| „Einheit … von … ist unbekannt, es wird Liter angenommen“ | Warnung | Der Wasserzähler hat eine Einheit, die die Integration nicht kennt (bekannt sind L, Liter, m³, ml) |
| „Nachgefüllt: … kg, im Behälter ist aber nur Platz für … kg …“ | Warnung | Du hast mehr eingetragen, als hineinpasst. Der Bestand wurde auf die Behältergröße begrenzt |

## Einen Fehler melden

Als [Issue](https://github.com/BeGiBue/water-softener-refill-sensor/issues) auf GitHub, mit:

1. Version der Integration (HACS) und von Home Assistant,
2. was du erwartet hast und was passiert ist,
3. den Zeilen aus dem Protokoll (mit Debug-Stufe),
4. dem Wert von „Verbrauch im Zeitfenster“ und der Einheit deines Wasserzählers.

## Grenzen

- **Es ist eine Näherung.** Die Integration sieht nicht die Anlage, sondern nur den Wasserverbrauch. Gleicht ein anderer nächtlicher Verbrauch dem Spülverbrauch der Regeneration, kann sie sich irren. Darum gibt es `add_regeneration` und `set_salt_stock`.
- **Der Zähler muss oft genug melden.** Wird nur stündlich aktualisiert, hängt der gesamte Verbrauch der Stunde an einem einzigen Zählerwert. Fällt der in das Fenster, zählt er voll, auch wenn der Verbrauch vorher entstand. Fällt er nicht hinein, geht er verloren.
- **Lücken zählen nicht.** Nach einem Neustart oder wenn der Zähler „nicht verfügbar“ war, wird nur ein neuer Bezugswert gesetzt. Verbrauch in der Lücke wird bewusst nicht gewertet.
- **Konstanter Salzverbrauch.** Die Integration rechnet mit festen Kilogramm je Regeneration. Der Bestand ersetzt keinen Blick in den Behälter.
- **Kein Zeitfenster über Mitternacht.** Beginn muss vor dem Ende liegen (nur volle Stunden, 0 bis 23 Uhr).
- **Hygieneregeneration wird nicht automatisch gezählt.** Sie wird nur gemeldet, wenn sie ausbleibt.
- **Nur eine Quelle:** Ein Wasserzähler je Anlage. Mehrere Anlagen sind durch mehrere Einträge möglich.
- **Alltagstauglichkeit der Erkennung:** Einrichtung, Optionen, Entitäten, Tasten und Dienste wurden ab 1.1.1 mit einem echten Home Assistant (2026.2) geprüft. Wie gut die Erkennung über viele Nächte arbeitet, hängt von deinem Wasserzähler ab (siehe oben).
