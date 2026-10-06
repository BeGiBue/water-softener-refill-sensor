# Entitäten und Dienste

Nachschlagewerk. Alle Entitäten gehören zu **einem Gerät** mit dem Namen, den du bei der Einrichtung vergeben hast. Die genauen Entitäts-IDs hängen von Name und Sprache ab: *Einstellungen → Geräte & Dienste → Entitäten*.

## Sensoren

| Name | Einheit / Typ | Bedeutung |
|---|---|---|
| **Regenerationen gesamt** | Zahl, steigend | Alle erkannten und nachgetragenen Regenerationen seit der Einrichtung |
| **Regenerationen seit Nachfüllen** | Zahl | Regenerationen seit der Behälter zuletzt **voll** war (siehe [Funktionsweise](Funktionsweise#4-nachfüllen-bestätigen)) |
| **Salzbestand** | kg | Rechnerischer Bestand. Zusatzattribute: `capacity_kg`, `per_regeneration_kg` |
| **Salzfüllstand** | % | Bestand im Verhältnis zur Behältergröße |
| **Restbestand Regenerationen** | Zahl | Für wie viele Regenerationen das Salz noch reicht (abgerundet). Zusatzattribut: `warn_at` (Warnschwelle) |
| **Letzte Regeneration** | Zeitstempel | Zeitpunkt, an dem der Schwellwert überschritten wurde. Zusatzattribut: `history` (die letzten 10) |
| **Nächste Regeneration spätestens** | Zeitstempel | 7 Tage nach der letzten Regeneration, zu Beginn des Zeitfensters. Leer, solange noch keine Regeneration bekannt ist |
| **Letztes Nachfüllen** | Zeitstempel, Diagnose | Wann zuletzt Salz bestätigt wurde |
| **Verbrauch im Zeitfenster** | Liter, Diagnose | Wasserverbrauch des laufenden oder zuletzt ausgewerteten Zeitfensters. Leer, solange noch kein Fenster erfasst wurde |

## Binärsensoren

| Name | Typ | An, wenn … |
|---|---|---|
| **Salz nachfüllen** | Problem | der Restbestand die Warnschwelle erreicht oder unterschreitet. Attribute: `regenerations_left`, `salt_stock_kg` |
| **Regeneration überfällig** | Problem | der 7-Tage-Fälligkeitstag vorbei ist und keine Regeneration erkannt wurde. Attribut: `next_regeneration_due` |

## Eingaben

| Name | Einheit | Bedeutung |
|---|---|---|
| **Nachgefüllte Salzmenge** | kg | Zahlenfeld von 0 bis zur Behältergröße in 0,5-kg-Schritten. Die Menge, die mit der Taste „Salz nachgefüllt“ bestätigt wird. Springt nach dem Bestätigen auf 0. **Wird nicht gespeichert:** Nach einem Neustart steht sie wieder auf 0 |
| **Letzte Regeneration korrigieren** | Datum und Uhrzeit (Konfiguration) | Zeitpunkt der letzten Regeneration von Hand setzen, zum Beispiel vom Display der Anlage. Bestimmt „Nächste Regeneration spätestens“ und „Regeneration überfällig“. Zählt keine Regeneration (ab 1.2.0) |
| **Regenerationen seit Nachfüllen korrigieren** | Zahl (Konfiguration) | Bekannte Regenerationen seit dem letzten Füllen bis voll. Der Salzbestand wird daraus berechnet: Behältergröße − Anzahl × Salzverbrauch pro Regeneration (ab 1.2.0) |

## Tasten

| Name | Wirkung |
|---|---|
| **Salz nachgefüllt** | Addiert die eingegebene Menge zum Bestand. Bei Menge 0 passiert nichts außer einer Fehlermeldung. Zähler „seit Nachfüllen“ wird nur auf 0 gesetzt, wenn der Behälter danach voll ist |
| **Behälter voll** | Setzt den Bestand auf die Behältergröße und den Zähler „seit Nachfüllen“ auf 0, ohne Mengeneingabe |

Beide Tasten setzen „Letztes Nachfüllen“ auf den aktuellen Zeitpunkt, löschen die Eingabe und aktualisieren die Meldung.

## Dienste (Aktionen)

Zu finden unter *Entwicklerwerkzeuge → Aktionen* und in Automationen. Sind **mehrere Anlagen** eingerichtet, muss zusätzlich `config_entry` angegeben werden. Bei genau einer Anlage ist das nicht nötig.

### `water_softener_refill_sensor.refill`: Nachfüllen bestätigen

| Feld | Pflicht | Beschreibung |
|---|---|---|
| `kg` | ja | Nachgefüllte Menge in kg, größer als 0. Wird zum Bestand addiert, höchstens bis zur Behältergröße |

Ohne `kg` oder mit 0 gibt es eine Fehlermeldung, und es ändert sich nichts.

### `water_softener_refill_sensor.set_salt_stock`: Bestand setzen

| Feld | Pflicht | Beschreibung |
|---|---|---|
| `kg` | ja | Neuer Bestand in kg, mindestens 0. Wird auf die Behältergröße begrenzt |

Ändert nur den Bestand, **nicht** die Zähler und nicht „Letztes Nachfüllen“.

### `water_softener_refill_sensor.add_regeneration`: Regeneration nachtragen

| Feld | Pflicht | Beschreibung |
|---|---|---|
| `count` | nein | Anzahl, 1 bis 100, Standard 1 |

Erhöht beide Zähler, zieht je Regeneration den Salzverbrauch ab und setzt „Letzte Regeneration“ auf den aktuellen Zeitpunkt.

### `water_softener_refill_sensor.set_last_regeneration`: Letzte Regeneration setzen (ab 1.2.0)

| Feld | Pflicht | Beschreibung |
|---|---|---|
| `datetime` | ja | Zeitpunkt der letzten Regeneration, nicht in der Zukunft. Ohne Zeitzone gilt Ortszeit |

Zähler und Salzbestand bleiben unverändert.

### `water_softener_refill_sensor.set_regenerations_since_refill`: Regenerationen seit Nachfüllen setzen (ab 1.2.0)

| Feld | Pflicht | Beschreibung |
|---|---|---|
| `count` | ja | Anzahl, 0 bis 1000 |

Der Salzbestand wird neu berechnet (Behältergröße − Anzahl × Verbrauch). Der Gesamtzähler wird bei Bedarf auf mindestens `count` angehoben.

## Einstellungen

Siehe [Installation und Einrichtung](Installation-und-Einrichtung#einrichtung). Alle Werte außer Name und Anfangsbestand sind im Nachhinein über **Konfigurieren** änderbar.

## Meldungen

| Meldung | Kennung | Sprache |
|---|---|---|
| Salz nachfüllen | `water_softener_refill_sensor_<Eintrags-ID>_low_salt` | Deutsch oder Englisch nach der Home-Assistant-Sprache |
| Regeneration überfällig | `water_softener_refill_sensor_<Eintrags-ID>_overdue` | wie oben |

Mit der Kennung lässt sich eine Meldung in Automationen gezielt über `persistent_notification.dismiss` entfernen. Normalerweise ist das nicht nötig, die Integration räumt selbst auf.
